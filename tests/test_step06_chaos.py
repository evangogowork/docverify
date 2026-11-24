"""(a) duplicates + killed workers never double-process a case; (c) per-account order holds;
bounded retries end in the DLQ. The failure controls live in test_controls.py."""
import collections
import json
import os
import random
import signal
import threading
import time

from fastapi.testclient import TestClient

from docverify import accounts, cases, db, samples, states
from docverify.config import settings
from docverify.api.main import app
from docverify.aws import queue_url, sqs

from .helpers import drain, upload, wait_state
from .workers import start_worker, stop

DONE = states.PIPELINE_DONE
ACCTS = ["acct_1001", "acct_1003", "acct_1008", "acct_1009"]   # names OCR reads cleanly; see chapter 10


def genuine(acct: str, i: int) -> tuple[bytes, str, str]:
    """A correct document for the account (valid check digit, in date): the expected outcome is APPROVED."""
    a = accounts.get(acct)
    return samples.make("clean" if i % 2 else "pdf", a, seed=i)


def resend_duplicate(case_id: str, n: int) -> None:
    """A duplicate the FIFO dedup window does not catch (e.g. a replayed event an hour later)."""
    c = cases.get_case(case_id)
    body = {"case_id": case_id, "account_id": c["account_id"], "round": c["round"], "bucket": "docverify-intake",
            "key": c["s3_key"], "sha256": c["sha256"], "enqueued_at": time.time()}
    sqs().send_message(QueueUrl=queue_url(), MessageBody=json.dumps(body), MessageGroupId=c["account_id"],
                       MessageDeduplicationId=f"{case_id}-replay{n}")


def transition_counts(case_ids):
    rows = db.query("SELECT case_id, round_no, from_state, to_state, COUNT(*) n FROM audit_log WHERE case_id IN %s"
                    " GROUP BY case_id, round_no, from_state, to_state", (tuple(case_ids),))
    return {(r["case_id"], r["round_no"], r["from_state"], r["to_state"]): r["n"] for r in rows}


def run_chaos(env: dict | None = None, n_docs=16, dup=2, kill_for=20.0, seed=7):
    """Upload docs, replay duplicates, SIGKILL random workers while they work. Returns the case ids."""
    rng = random.Random(seed)
    drain()
    # Extraction takes 0.2-9s; the visibility timeout is 6s, so some messages are redelivered to a
    # second worker while the first is still extracting (a GC pause, a stuck network call).
    env = {"DOCVERIFY_TEST_SLOW_EXTRACT": "0.2-8", **(env or {})}
    procs = [start_worker(f"chaos-{i}", env) for i in range(5)]
    kills = 0
    try:
        c = TestClient(app)
        ids = []
        for i in range(n_docs):
            acct = ACCTS[i % len(ACCTS)]
            data, ctype, name = genuine(acct, i)
            ids.append(upload(c, acct, data, name, ctype))
        for cid in ids:
            wait_state(cid, {"QUEUED"} | DONE | {"EXTRACTED", "VALIDATED"}, 60)
            for k in range(dup):
                resend_duplicate(cid, k)
        t_end = time.time() + kill_for
        gen = len(procs)
        while time.time() < t_end:
            time.sleep(rng.uniform(0.6, 1.6))
            victim = rng.randrange(len(procs))
            os.kill(procs[victim].pid, signal.SIGKILL)
            procs[victim].wait()
            kills += 1
            procs[victim] = start_worker(f"chaos-{gen}", env)
            gen += 1
        for cid in ids:
            wait_state(cid, DONE, 120)
        states.reconcile(ids)
        return ids, kills
    finally:
        stop(procs)


# @learn:test-chaos
def test_duplicates_and_kills_never_double_process():
    ids, kills = run_chaos()
    assert kills >= 8
    counts = transition_counts(ids)
    doubled = {k: n for k, n in counts.items() if n > 1}
    assert doubled == {}, f"transitions committed more than once: {doubled}"
    for cid in ids:
        c = cases.get_case(cid)
        hist = [(h["round"], h["from"], h["to"]) for h in c["history"]]
        assert len(hist) == len(set(hist)), hist
        assert len(states.audit_rows(cid)) == len(hist)
        # Not just "finished": every genuine document reached the right decision, none dead-lettered.
        assert c["state"] == "APPROVED", (cid, c["state"], c.get("decision_detail"))
# @learn:end test-chaos


def test_lock_expiring_mid_extraction_still_commits_once():
    """The Redis lock is only a lease. Every extraction here takes 7.5s, past both the 2s lock TTL and
    the 6s visibility timeout, so an idle worker gets the redelivered copy, takes the expired lock and
    runs the same stage at the same time. Only the conditional write keeps the case consistent."""
    drain()
    env = {"DOCVERIFY_TEST_SLOW_EXTRACT": "7.5", "DOCVERIFY_LOCK_TTL": "2"}
    procs = [start_worker(f"lease-{i}", env) for i in range(6)]
    try:
        c = TestClient(app)
        ids = []
        for a in ACCTS[:3]:
            data, ctype, name = genuine(a, 1)
            ids.append(upload(c, a, data, name, ctype))
        for cid in ids:
            wait_state(cid, {"APPROVED", "REJECTED", "IN_REVIEW", "FAILED"}, 120)
        time.sleep(12)                                      # let the slower copy finish too
        runs = db.query("SELECT case_id, COUNT(*) n FROM extraction_runs WHERE case_id IN %s GROUP BY case_id",
                        (tuple(ids),))
        assert any(r["n"] > 1 for r in runs), "scenario did not produce concurrent copies"   # the test is live
        doubled = {k: n for k, n in transition_counts(ids).items() if n > 1}
        assert doubled == {}, f"transitions committed more than once: {doubled}"
        assert all(cases.get_case(cid)["state"] == "APPROVED" for cid in ids)
    finally:
        stop(procs)


def test_concurrent_copies_do_not_redo_extraction():
    """A copy redelivered while the first worker is still extracting backs off instead of extracting again."""
    drain()
    env = {"DOCVERIFY_TEST_SLOW_EXTRACT": "8"}   # longer than the 6s visibility timeout
    procs = [start_worker(f"slow-{i}", env) for i in range(5)]   # idle workers pick up the redelivered copies
    try:
        c = TestClient(app)
        ids = [upload(c, a, genuine(a, 2)[0], "d.pdf", "application/pdf") for a in ACCTS[:3]]
        for cid in ids:
            wait_state(cid, DONE, 90)
        runs = db.query("SELECT case_id, COUNT(*) n FROM extraction_runs WHERE case_id IN %s GROUP BY case_id",
                        (tuple(ids),))
        assert {r["case_id"]: r["n"] for r in runs} == {cid: 1 for cid in ids}
    finally:
        stop(procs)


def test_per_account_order_is_preserved():
    """(c) Five documents for one account are extracted in the order they were enqueued."""
    drain()
    procs = [start_worker(f"order-{i}", {"DOCVERIFY_TEST_SLOW_EXTRACT": "0.3"}) for i in range(3)]
    try:
        c = TestClient(app)
        ids = []
        for i in range(5):
            ids.append(upload(c, "acct_1001", genuine("acct_1001", 2 * i)[0], f"o{i}.pdf", "application/pdf"))
            wait_state(ids[-1], {"QUEUED"} | DONE | {"EXTRACTED", "VALIDATED"}, 60)
        for cid in ids:
            wait_state(cid, DONE, 90)
        firsts = []
        for cid in ids:
            row = db.query("SELECT id FROM audit_log WHERE case_id=%s AND to_state='EXTRACTED' ORDER BY id LIMIT 1",
                           (cid,))
            firsts.append(row[0]["id"])
        assert firsts == sorted(firsts)
    finally:
        stop(procs)


def test_poison_message_is_dead_lettered_after_bounded_retries():
    drain()
    procs = [start_worker("poison-0")]
    try:
        c = TestClient(app)
        cid = upload(c, "acct_1001", b"\x89PNG\r\n\x1a\n" + b"not really a png" * 10, "x.png", "image/png")
        case = wait_state(cid, {"FAILED"}, 120)
        receipts = db.query("SELECT MAX(receive_count) m FROM queue_receipts WHERE case_id=%s", (cid,))
        assert receipts[0]["m"] == settings().max_receives        # maxReceiveCount, then the DLQ
        assert states.audit_rows(cid)[-1]["reason"].startswith("dead-letter")
        assert case["state"] == "FAILED"
    finally:
        stop(procs)
