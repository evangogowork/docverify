import json
import time

from fastapi.testclient import TestClient

from docverify import cases
from docverify.aws import queue_url, sqs


def upload(client: TestClient, account_id: str, body: bytes, name="doc.txt", ctype="text/plain",
           doc_type="business_license", headers=None) -> str:
    r = client.post("/v1/cases", data={"account_id": account_id, "doc_type": doc_type},
                    files={"file": (name, body, ctype)}, headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()["case_id"]


def wait_state(case_id: str, states: set[str], timeout=60.0) -> dict:
    t = time.time()
    while time.time() - t < timeout:
        c = cases.get_case(case_id)
        if c and c["state"] in states:
            return c
        time.sleep(0.3)
    raise AssertionError(f"{case_id} stuck in {cases.get_case(case_id)['state']}, wanted {states}")


def drain(queue: str | None = None) -> list[dict]:
    """Receive and delete everything currently on a queue (tests that inspect the queue directly)."""
    url = queue_url(queue)
    out = []
    while True:
        r = sqs().receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=1,
                                  AttributeNames=["All"])
        msgs = r.get("Messages", [])
        if not msgs:
            return out
        for m in msgs:
            out.append({"body": json.loads(m["Body"]), "attrs": m["Attributes"]})
            sqs().delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
