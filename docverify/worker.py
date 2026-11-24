"""Pipeline worker: consumes the SQS FIFO queue and drives a case through extraction and validation.

Run several of these; FIFO message groups (one per account) keep each account's cases in order
while different accounts are processed in parallel. A worker only ever moves a case forward with a
conditional transition, so two workers holding the same message cannot both commit a stage.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import signal
import socket
import time

from botocore.exceptions import ClientError

from . import accounts, cases, db, dedup, states
from .aws import client, queue_url, s3, sqs
from .config import settings
from .extract import Extraction, UnsupportedFormat, get_extractor
from .pipeline import matches_for
from .decide import decide
from .validate import validate


class Worker:
    def __init__(self, worker_id: str | None = None):
        self.id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.extractor = get_extractor()
        self.stopping = False
        # Test hook: "2" sleeps 2s inside extraction, "0.2-9" sleeps a random amount in that range —
        # some of it past the visibility timeout, which is exactly when SQS hands the same message
        # to a second worker while the first is still working on it.
        lo, _, hi = os.environ.get("DOCVERIFY_TEST_SLOW_EXTRACT", "0").partition("-")
        self.slow_range = (float(lo), float(hi or lo))

    # ---- one case ---------------------------------------------------------------------------
    # @learn:worker-process
    def process(self, msg: dict) -> str:
        """Advance the case as far as the automated pipeline goes. Returns an outcome label."""
        body = json.loads(msg["Body"])
        cid, rnd = body["case_id"], int(body["round"])
        case = cases.get_case(cid)
        if case is None:
            return "missing"
        if int(case["round"]) != rnd:
            return "stale-round"   # a message for a superseded submission
        while case["state"] not in states.PIPELINE_DONE:
            step = getattr(self, "_step_" + case["state"].lower(), None)
            if step is None:
                return "waiting:" + case["state"]
            try:
                case = step(case, body)
            except states.Conflict:
                return "conflict"     # someone else advanced it; never commit on top of them
        return "done"
    # @learn:end worker-process

    def _step_queued(self, case: dict, body: dict) -> dict:
        data = s3().get_object(Bucket=body["bucket"], Key=body["key"])["Body"].read()
        db.execute("INSERT INTO extraction_runs (case_id, round_no, worker_id, engine) VALUES (%s,%s,%s,%s)",
                   (case["case_id"], case["round"], self.id, self.extractor.name))
        if self.slow_range[1]:
            time.sleep(random.uniform(*self.slow_range))
        try:
            ex = self.extractor.extract(data, case.get("content_type", "application/octet-stream"))
        except UnsupportedFormat as e:
            return states.transition(case["case_id"], "QUEUED", "RESUBMIT_REQUESTED", round_no=case["round"],
                                     actor=f"worker:{self.id}", reason="unsupported_format",
                                     updates={"decision_detail": {"reasons": [str(e)]}})
        return states.transition(case["case_id"], "QUEUED", "EXTRACTED", round_no=case["round"],
                                 actor=f"worker:{self.id}", reason=ex.engine,
                                 updates={"extraction": ex.to_dict()},
                                 detail={"fields": {k: [v.value, v.confidence] for k, v in ex.fields.items()}})

    def _step_extracted(self, case: dict, body: dict) -> dict:
        ex = Extraction.from_dict(case["extraction"])
        checks = [c.to_dict() for c in validate(ex, case["doc_type"])]
        failed = [c["name"] for c in checks if not c["passed"]]
        return states.transition(case["case_id"], "EXTRACTED", "VALIDATED", round_no=case["round"],
                                 actor=f"worker:{self.id}", reason=f"{len(failed)} failed checks",
                                 updates={"validation": checks}, detail={"failed": failed})

    # @learn:worker-decide
    def _step_validated(self, case: dict, body: dict) -> dict:
        ex = Extraction.from_dict(case["extraction"])
        account = accounts.get(case["account_id"])
        matches = matches_for(ex, account, accounts.alias_index())
        d = decide(case["validation"], matches)
        if account is None:
            d = {**d, "decision": "IN_REVIEW", "automated": False, "reasons": ["unknown_account", *d["reasons"]]}
        return states.transition(case["case_id"], "VALIDATED", d["decision"], round_no=case["round"],
                                 actor=f"worker:{self.id}", reason=",".join(d["reasons"])[:255] or "all checks passed",
                                 updates={"matches": matches, "decision_detail": d, "risk_score": d["risk"],
                                          "review_enqueued_at": cases.now()},
                                 detail={"decision": d, "matches": matches})
    # @learn:end worker-decide

    # ---- the loop ---------------------------------------------------------------------------
    # @learn:worker-handle
    def handle(self, msg: dict) -> str:
        body = json.loads(msg["Body"])
        cid, rnd = body["case_id"], int(body["round"])
        attrs = msg.get("Attributes", {})
        with db.conn().cursor() as cur:
            cur.execute(
                "INSERT INTO queue_receipts (case_id, round_no, message_id, group_id, sequence_number, receive_count,"
                " worker_id, body) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (cid, rnd, msg["MessageId"], attrs.get("MessageGroupId", ""), attrs.get("SequenceNumber", ""),
                 int(attrs.get("ApproximateReceiveCount", 1)), self.id, msg["Body"]))
            msg["_receipt_row"] = cur.lastrowid
        if dedup.is_done(cid, rnd):
            self._ack(msg)
            return "dedup:done"     # a duplicate of finished work: drop it
        if not dedup.acquire(cid, rnd, self.id):
            return "dedup:locked"          # another worker has it; this copy comes back later
        try:
            outcome = self.process(msg)
            if outcome in ("done", "missing", "stale-round"):
                dedup.mark_done(cid, rnd)
                if not self._ack(msg):
                    outcome += "+stale-receipt"
            return outcome
        finally:
            dedup.release(cid, rnd, self.id)
    # @learn:end worker-handle

    def _ack(self, msg: dict) -> bool:
        try:
            sqs().delete_message(QueueUrl=queue_url(), ReceiptHandle=msg["ReceiptHandle"])
            return True
        except ClientError as e:
            # The message was redelivered while we worked, so our receipt handle is stale. The worker
            # holding the newer copy will see the done key and delete it.
            if e.response["Error"]["Code"] in ("InvalidParameterValue", "ReceiptHandleIsInvalid"):
                return False
            raise

    def _retry_later(self, msg: dict) -> None:
        """Bounded retry with exponential backoff; SQS's redrive policy moves it to the DLQ after max receives."""
        n = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", 1))
        base = float(os.environ.get("DOCVERIFY_RETRY_BASE", "2"))
        cap = float(os.environ.get("DOCVERIFY_RETRY_CAP", "300"))
        delay = int(min(cap, base * (2 ** (n - 1))))
        try:
            sqs().change_message_visibility(QueueUrl=queue_url(), ReceiptHandle=msg["ReceiptHandle"],
                                            VisibilityTimeout=delay)
        except Exception:
            pass

    # @learn:dlq
    def drain_dlq(self) -> int:
        """Cases whose message exhausted its retries end in FAILED, with the reason in the audit log."""
        url = queue_url(settings().dlq)
        msgs = sqs().receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=0,
                                     AttributeNames=["All"]).get("Messages", [])
        for m in msgs:
            body = json.loads(m["Body"])
            case = cases.get_case(body["case_id"])
            if case and int(case["round"]) == int(body["round"]) and "FAILED" in states.TRANSITIONS[case["state"]]:
                try:
                    states.transition(case["case_id"], case["state"], "FAILED", round_no=case["round"],
                                      actor=f"worker:{self.id}", reason="dead-letter: retries exhausted",
                                      detail={"receives": m["Attributes"].get("ApproximateReceiveCount")})
                except states.Conflict:
                    pass
            sqs().delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
        return len(msgs)
    # @learn:end dlq

    # @learn:sweeper
    def sweep(self) -> None:
        """Background job: re-drive cases whose S3 event never produced a message, and back-fill audit rows."""
        if not dedup.singleton("sweeper", 10):
            return
        stuck_after = float(os.environ.get("DOCVERIFY_STUCK_AFTER", "30"))
        for c in cases.scan_cases(1000):
            if c["state"] == "UPLOADED" and c.get("s3_key") and cases.now() - float(c.get("updated_at", 0)) > stuck_after:
                event = {"Records": [{"s3": {"bucket": {"name": settings().bucket}, "object": {"key": c["s3_key"]}}}]}
                client("lambda").invoke(FunctionName=settings().lambda_name, InvocationType="Event",
                                        Payload=json.dumps(event).encode())
                print(json.dumps({"worker": self.id, "redrive": c["case_id"]}), flush=True)
        states.reconcile()
    # @learn:end sweeper

    def run_once(self, wait: int = 2) -> int:
        # Take only what we can finish inside the visibility timeout. Prefetching ten and working through
        # them one by one lets the tail of the batch time out and get redelivered, and a killed worker
        # burns a receive on every message it was holding.
        batch = int(os.environ.get("DOCVERIFY_RECEIVE_BATCH", "1"))
        r = sqs().receive_message(QueueUrl=queue_url(), MaxNumberOfMessages=batch, WaitTimeSeconds=wait,
                                  AttributeNames=["All"])
        msgs = r.get("Messages", [])
        for m in msgs:
            try:
                outcome = self.handle(m)
            except Exception as e:  # not acked: retried with backoff, then dead-lettered
                outcome = f"error:{type(e).__name__}:{str(e)[:120]}"
                self._retry_later(m)
            if m.get("_receipt_row"):
                db.execute("UPDATE queue_receipts SET outcome=%s WHERE id=%s", (outcome[:32], m["_receipt_row"]))
            print(json.dumps({"worker": self.id, "case": json.loads(m["Body"])["case_id"], "outcome": outcome}),
                  flush=True)
        return len(msgs)

    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stopping", True))
        print(json.dumps({"worker": self.id, "started": True, "queue": settings().queue}), flush=True)
        last_sweep = 0.0
        while not self.stopping:
            self.run_once()
            self.drain_dlq()
            if time.time() - last_sweep > 5:
                last_sweep = time.time()
                try:
                    self.sweep()
                except Exception as e:
                    print(json.dumps({"worker": self.id, "sweep_error": str(e)[:200]}), flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--id")
    a = p.parse_args()
    Worker(a.id).run()


if __name__ == "__main__":
    main()
