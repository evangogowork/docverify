"""Learn mode: reconstruct where one case is in the pipeline, from the real stores.

Nothing here is simulated. Each stage's status is derived from the case's DynamoDB history, and its
data is read from where that stage left it: S3 object metadata, the Lambda's CloudWatch log, the
queue receipts the workers recorded, the MySQL audit rows, the callback outbox and the platform's
receiver.
"""
from __future__ import annotations

import json
import os

import httpx

from . import cases, db, states
from .aws import client, s3
from .config import settings

MOCK_PLATFORM = os.environ.get("DOCVERIFY_MOCK_PLATFORM", "http://127.0.0.1:8511")
SCENARIOS = {"clean": ("acct_1001", "clean"), "lowres": ("acct_1002", "lowres"), "tampered": ("acct_1003", "tampered")}


def _lambda_logs(case_id: str) -> list[str]:
    logs = client("logs")
    group = f"/aws/lambda/{settings().lambda_name}"
    try:
        streams = logs.describe_log_streams(logGroupName=group, orderBy="LastEventTime", descending=True,
                                            limit=5)["logStreams"]
    except Exception:
        return []
    for st in streams:
        events = logs.get_log_events(logGroupName=group, logStreamName=st["logStreamName"], limit=200)["events"]
        for i, e in enumerate(events):
            if case_id in e["message"]:
                start = max(0, i - 1)
                return [x["message"].rstrip() for x in events[start:i + 3]]
    return []


def _receiver(case_id: str) -> list[dict]:
    try:
        return httpx.get(f"{MOCK_PLATFORM}/received", params={"case_id": case_id}, timeout=2).json()["items"]
    except Exception:
        return []


# @learn:learn-trace
def trace(case_id: str) -> dict:
    c = cases.get_case(case_id)
    if c is None:
        raise KeyError(case_id)
    hist = c.get("history", [])
    audit = states.audit_rows(case_id)

    def step(frm=None, to=None):
        for h in hist:
            if (frm is None or h["from"] == frm) and (to is None or h["to"] == to):
                row = next((a for a in audit if a["write_id"] == h["write_id"]), None)
                return {"history": h, "audit": row}
        return None

    st: dict[str, dict] = {}
    up = step("NEW", "UPLOADED")
    st["upload"] = {"done": bool(up), "at": up["history"]["at"] if up else None,
                    "data": None if not up else {"s3_key": c["s3_key"], "sha256": c["sha256"], "content_type": c["content_type"],
                                    "platform": c.get("platform"), "audit": up["audit"]}}
    try:
        head = s3().head_object(Bucket=settings().bucket, Key=c["s3_key"])
        st["s3"] = {"done": True, "data": {"bucket": settings().bucket, "key": c["s3_key"], "size": head["ContentLength"],
                                           "etag": head["ETag"], "metadata": head["Metadata"],
                                           "event": "s3:ObjectCreated:Put -> lambda " + settings().lambda_name}}
    except Exception:
        st["s3"] = {"done": False}
    q = step("UPLOADED", "QUEUED")
    st["lambda"] = {"done": bool(q), "at": q["history"]["at"] if q else None,
                    "data": None if not q else {"audit": q["audit"], "logs": _lambda_logs(case_id)}}
    receipts = db.query("SELECT id, message_id, group_id, sequence_number, receive_count, worker_id, outcome,"
                        " body, received_at FROM queue_receipts WHERE case_id=%s ORDER BY id", (case_id,))
    for r in receipts:
        r["body"] = json.loads(r["body"])
    st["sqs"] = {"done": bool(receipts), "at": receipts[0]["received_at"].timestamp() if receipts else None,
                 "data": {"receipts": receipts} if receipts else None}
    ex = step("QUEUED", "EXTRACTED") or step("QUEUED", "RESUBMIT_REQUESTED")
    st["extraction"] = {"done": bool(ex), "at": ex["history"]["at"] if ex else None,
                        "data": None if not ex else {"extraction": c.get("extraction"), "audit": ex["audit"]}}
    va = step("EXTRACTED", "VALIDATED")
    st["validation"] = {"done": bool(va), "skipped": bool(ex) and ex["history"]["to"] == "RESUBMIT_REQUESTED",
                        "at": va["history"]["at"] if va else None, "data": None if not va else {"checks": c.get("validation"), "audit": va["audit"]}}
    de = step("VALIDATED", None)
    st["decision"] = {"done": bool(de), "at": de["history"]["at"] if de else None,
                      "data": None if not de else {"matches": c.get("matches"), "decision": c.get("decision_detail"), "audit": de["audit"]}}
    went_to_review = bool(step("VALIDATED", "IN_REVIEW"))
    rv = step("IN_REVIEW", None)
    st["review"] = {"done": bool(rv), "skipped": bool(de) and not went_to_review, "at": rv["history"]["at"] if rv else None,
                    "data": (went_to_review or None) and {"risk_score": c.get("risk_score"), "claimed_by": c.get("claimed_by"),
                                                           "review": c.get("review"), "audit": rv["audit"] if rv else None}}
    outbox = db.query("SELECT id, status, attempts, delivered_at, dead, last_error, payload FROM callback_outbox"
                      " WHERE case_id=%s ORDER BY id", (case_id,))
    for o in outbox:
        o["payload"] = json.loads(o["payload"])
        o["attempts_log"] = db.query("SELECT attempt, http_status, error, signature, sent_at FROM callback_attempts"
                                     " WHERE outbox_id=%s ORDER BY id", (o["id"],))
    final = c["state"] in states.TERMINAL or c["state"] == "RESUBMIT_REQUESTED"
    final_cb = [o for o in outbox if o["status"] == c["state"]]
    delivered = final_cb[0]["delivered_at"] if final_cb else None
    st["callback"] = {"done": final and bool(final_cb) and all(o["delivered_at"] for o in final_cb),
                      "at": delivered.timestamp() if delivered else None,
                      "data": {"outbox": outbox, "received_by_platform": _receiver(case_id)} if outbox else None}

    order = ["upload", "s3", "lambda", "sqs", "extraction", "validation", "decision", "review", "callback"]
    out, active_given = [], False
    for sid in order:
        s = st[sid]
        status = "done" if s.get("done") else "skipped" if s.get("skipped") else "pending"
        if status == "pending" and not active_given:
            status, active_given = "active", True
        out.append({"id": sid, "status": status, "at": s.get("at"), "data": s.get("data")})
    return {"case": c, "audit": audit, "stages": out}
# @learn:end learn-trace
