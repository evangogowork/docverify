"""Pipeline worker: consumes the SQS FIFO queue and drives a case through extraction and validation.

Run several of these; FIFO message groups (one per account) keep each account's cases in order
while different accounts are processed in parallel. A worker only ever moves a case forward with a
conditional transition, so two workers holding the same message cannot both commit a stage.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import time

from . import cases, db, states
from .aws import queue_url, s3, sqs
from .config import settings
from .extract import Extraction, UnsupportedFormat, get_extractor
from .validate import validate


class Worker:
    def __init__(self, worker_id: str | None = None):
        self.id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.extractor = get_extractor()
        self.stopping = False
        self.slow_extract = float(os.environ.get("DOCVERIFY_TEST_SLOW_EXTRACT", "0"))

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
    # @learn:end process

    def _step_queued(self, case: dict, body: dict) -> dict:
        data = s3().get_object(Bucket=body["bucket"], Key=body["key"])["Body"].read()
        db.execute("INSERT INTO extraction_runs (case_id, round_no, worker_id, engine) VALUES (%s,%s,%s,%s)",
                   (case["case_id"], case["round"], self.id, self.extractor.name))
        if self.slow_extract:
            time.sleep(self.slow_extract)
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

    # ---- the loop ---------------------------------------------------------------------------
    def handle(self, msg: dict) -> str:
        body = json.loads(msg["Body"])
        attrs = msg.get("Attributes", {})
        db.execute(
            "INSERT INTO queue_receipts (case_id, round_no, message_id, group_id, sequence_number, receive_count,"
            " worker_id, body) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (body["case_id"], body["round"], msg["MessageId"], attrs.get("MessageGroupId", ""),
             attrs.get("SequenceNumber", ""), int(attrs.get("ApproximateReceiveCount", 1)), self.id,
             msg["Body"]))
        outcome = self.process(msg)
        if outcome in ("done", "missing", "stale-round"):
            sqs().delete_message(QueueUrl=queue_url(), ReceiptHandle=msg["ReceiptHandle"])
        return outcome

    def run_once(self, wait: int = 2) -> int:
        r = sqs().receive_message(QueueUrl=queue_url(), MaxNumberOfMessages=10, WaitTimeSeconds=wait,
                                  AttributeNames=["All"])
        msgs = r.get("Messages", [])
        for m in msgs:
            try:
                outcome = self.handle(m)
            except Exception as e:  # leave the message: it becomes visible again and is retried
                outcome = f"error:{type(e).__name__}:{e}"
            print(json.dumps({"worker": self.id, "case": json.loads(m["Body"])["case_id"], "outcome": outcome}),
                  flush=True)
        return len(msgs)

    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stopping", True))
        print(json.dumps({"worker": self.id, "started": True, "queue": settings().queue}), flush=True)
        while not self.stopping:
            self.run_once()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--id")
    a = p.parse_args()
    Worker(a.id).run()


if __name__ == "__main__":
    main()
