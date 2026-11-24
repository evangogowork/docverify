import threading

import pytest
from fastapi.testclient import TestClient

from docverify import cases, states
from docverify.api.main import app, review_queue
from docverify.review import ReviewQueue

from .helpers import auth_headers, drain, reviewer_headers, upload, wait_state
from .workers import start_worker, stop


def test_heap_orders_by_risk_and_wait():
    q = ReviewQueue(aging=60)
    q.push("old_low", risk=10, enqueued_at=1000)       # waited longest, low risk
    q.push("new_high", risk=90, enqueued_at=4000)      # just arrived, high risk
    q.push("mid", risk=50, enqueued_at=2000)
    # key = t - 60*risk: old_low 400, new_high -1400, mid -1000
    assert [q.pop(), q.pop(), q.pop()] == ["new_high", "mid", "old_low"]


def test_aging_lets_a_low_risk_case_overtake():
    q = ReviewQueue(aging=60)
    q.push("low_but_ancient", risk=0, enqueued_at=0)
    q.push("high_recent", risk=40, enqueued_at=3000)   # 40 points = 2400s head start, but 3000s younger
    assert q.pop() == "low_but_ancient"


def test_lazy_deletion_and_repush():
    q = ReviewQueue()
    q.push("a", 10, 100)
    q.push("b", 20, 100)
    q.remove("b")
    q.push("a", 50, 100)          # re-prioritised: the stale entry is skipped
    assert q.pop() == "a" and q.pop() is None


def test_platform_auth_and_isolation():
    c = TestClient(app)
    assert c.post("/v1/cases", data={"account_id": "acct_1001", "doc_type": "business_license"},
                  files={"file": ("x.txt", b"x", "text/plain")}).status_code == 401
    assert c.post("/v1/auth/token", json={"client_id": "ecommerce-demo", "client_secret": "wrong"}).status_code == 401
    eco, ads = auth_headers("ecommerce"), auth_headers("ads")
    cid = upload(c, "acct_1001", b"hello", headers=eco)
    assert c.get(f"/v1/cases/{cid}", headers=eco).status_code == 200
    assert c.get(f"/v1/cases/{cid}", headers=ads).status_code == 404          # other platforms cannot see it
    r = c.post("/v1/cases", data={"account_id": "acct_1001", "doc_type": "business_license"},
               files={"file": ("x.txt", b"x", "text/plain")}, headers=ads)
    assert r.status_code == 403                                               # account belongs to ecommerce
    assert c.get("/v1/review/queue", headers=eco).status_code == 403          # platforms are not reviewers


def _in_review_case(c, headers) -> str:
    from docverify import accounts, samples
    data, ctype, name = samples.make("lowres", accounts.get("acct_1001"), seed=5)
    cid = upload(c, "acct_1001", data, name, ctype, headers=headers)
    wait_state(cid, {"IN_REVIEW", "APPROVED", "REJECTED", "RESUBMIT_REQUESTED"}, 60)
    assert cases.get_case(cid)["state"] == "IN_REVIEW"
    return cid


def test_review_claim_decide_and_resubmit():
    drain()
    w = start_worker("w-review")
    try:
        c = TestClient(app)
        eco, rev = auth_headers("ecommerce"), reviewer_headers()
        cid = _in_review_case(c, eco)
        claimed = None
        for _ in range(50):                      # other IN_REVIEW cases may be ahead in the heap
            r = c.post("/v1/review/claim", headers=rev)
            assert r.status_code == 200, r.text
            if r.json()["case_id"] == cid:
                claimed = r.json()
                break
            c.post(f"/v1/review/cases/{r.json()['case_id']}/decision", headers=rev,
                   json={"decision": "RESUBMIT_REQUESTED", "reason": "test sweep"})
        assert claimed and claimed["claimed_by"] == "reviewer"
        # Someone else cannot decide a case they did not claim.
        from docverify import auth
        auth.create_reviewer("reviewer2", "reviewer2-test-pass")
        rev2 = {"Authorization": "Bearer " + c.post("/v1/auth/login", json={"username": "reviewer2",
                                                    "password": "reviewer2-test-pass"}).json()["access_token"]}
        assert c.post(f"/v1/review/cases/{cid}/decision", headers=rev2,
                      json={"decision": "APPROVED"}).status_code == 409
        r = c.post(f"/v1/review/cases/{cid}/decision", headers=rev,
                   json={"decision": "RESUBMIT_REQUESTED", "reason": "image unreadable, please rescan"})
        assert r.status_code == 200 and r.json()["state"] == "RESUBMIT_REQUESTED"
        # The platform resubmits: round 2 goes through the whole pipeline again.
        from docverify import accounts, samples
        data, ctype, name = samples.make("pdf", accounts.get("acct_1001"), seed=6)
        r = c.post(f"/v1/cases/{cid}/resubmit", files={"file": (name, data, ctype)}, headers=eco)
        assert r.status_code == 200 and r.json()["round"] == 2
        final = wait_state(cid, {"APPROVED"}, 60)
        assert final["round"] == 2
        rounds = [(h["round"], h["from"], h["to"]) for h in final["history"]]
        assert (1, "IN_REVIEW", "RESUBMIT_REQUESTED") in rounds and (2, "VALIDATED", "APPROVED") in rounds
    finally:
        stop([w])


def test_two_reviewers_never_claim_the_same_case():
    drain()
    w = start_worker("w-claims")
    try:
        c = TestClient(app)
        eco, rev = auth_headers("ecommerce"), reviewer_headers()
        ids = {_in_review_case(c, eco) for _ in range(3)}
        got, lock = [], threading.Lock()

        def grab():
            r = c.post("/v1/review/claim", headers=rev)
            if r.status_code == 200:
                with lock:
                    got.append(r.json()["case_id"])

        ts = [threading.Thread(target=grab) for _ in range(12)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert len(got) == len(set(got))                 # no case handed out twice
        assert ids <= set(got) or len(got) >= len(ids)
    finally:
        stop([w])
