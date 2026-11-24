"""S3-triggered intake Lambda.

ObjectCreated -> read the object's metadata -> move the case UPLOADED -> QUEUED -> send one
SQS FIFO message with MessageGroupId = account_id (per-account ordering) and a deterministic
MessageDeduplicationId (SQS drops a re-send of the same case round for five minutes).
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse

from docverify import cases, states
from docverify.aws import queue_url, s3, sqs


# @learn:lambda-intake
def handle_record(bucket: str, key: str) -> dict:
    head = s3().head_object(Bucket=bucket, Key=key)
    meta = head.get("Metadata", {})
    case_id, account_id, round_no = meta["case_id"], meta["account_id"], int(meta.get("round", "1"))
    body = s3().get_object(Bucket=bucket, Key=key)["Body"].read()
    sha = hashlib.sha256(body).hexdigest()
    try:
        states.transition(case_id, "UPLOADED", "QUEUED", round_no=round_no, actor="lambda:intake",
                          reason="s3:ObjectCreated", detail={"bucket": bucket, "key": key})
    except states.Conflict as c:
        # A retried S3 event: the case is already QUEUED for this round, so just (re)send.
        current = cases.get_case(case_id)
        if not (c.actual == "QUEUED" and current and current.get("round") == round_no):
            print(json.dumps({"skip": case_id, "state": c.actual}))
            return {"skipped": case_id}
    message = {"case_id": case_id, "account_id": account_id, "round": round_no,
               "bucket": bucket, "key": key, "sha256": sha, "enqueued_at": time.time()}
    r = sqs().send_message(
        QueueUrl=queue_url(), MessageBody=json.dumps(message),
        MessageGroupId=account_id,                       # per-account ordering
        MessageDeduplicationId=f"{case_id}-r{round_no}",  # SQS-level duplicate suppression
    )
    print(json.dumps({"queued": case_id, "group": account_id, "message_id": r["MessageId"]}))
    return {"queued": case_id, "message_id": r["MessageId"]}
# @learn:end lambda-intake


def handler(event, context):
    out = []
    for rec in event.get("Records", []):
        bucket = rec["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
        out.append(handle_record(bucket, key))
    return {"results": out}
