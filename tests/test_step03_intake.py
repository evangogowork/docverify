from fastapi.testclient import TestClient

from docverify import states
from docverify.api.main import app

from .helpers import drain, upload, wait_state


def test_s3_event_runs_lambda_and_enqueues_per_account():
    drain()
    c = TestClient(app)
    ids = [upload(c, "acct_q1", b"one"), upload(c, "acct_q2", b"two"), upload(c, "acct_q1", b"three")]
    for cid in ids:
        wait_state(cid, {"QUEUED"})
    msgs = []
    for _ in range(10):
        msgs += drain()
        if len(msgs) >= 3:
            break
    by_case = {m["body"]["case_id"]: m for m in msgs}
    assert set(ids) <= set(by_case)
    for cid in ids:
        m = by_case[cid]
        assert m["attrs"]["MessageGroupId"] == m["body"]["account_id"]
        assert m["attrs"]["MessageDeduplicationId"] == f"{cid}-r1"
        actors = [(r["from_state"], r["to_state"], r["actor"]) for r in states.audit_rows(cid)]
        assert actors == [("NEW", "UPLOADED", "api"), ("UPLOADED", "QUEUED", "lambda:intake")]
