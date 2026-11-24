import threading

import pytest

from docverify import cases, states


def _case(state="VALIDATED"):
    cid = cases.new_case_id()
    cases.put_new_case({"case_id": cid, "account_id": "acct_t", "doc_type": "business_license",
                        "state": state, "round": 1, "created_at": cases.now()})
    return cid


def test_legal_transition_commits_and_audits():
    cid = _case("UPLOADED")
    states.transition(cid, "UPLOADED", "QUEUED", round_no=1, actor="test")
    c = cases.get_case(cid)
    assert c["state"] == "QUEUED" and len(c["history"]) == 1
    rows = states.audit_rows(cid)
    assert [(r["from_state"], r["to_state"]) for r in rows] == [("UPLOADED", "QUEUED")]


def test_illegal_transition_rejected_before_any_write():
    cid = _case("APPROVED")
    with pytest.raises(states.IllegalTransition):
        states.transition(cid, "APPROVED", "UPLOADED", round_no=1, actor="test")
    assert states.audit_rows(cid) == []


def test_stale_from_state_is_a_conflict():
    cid = _case("UPLOADED")
    with pytest.raises(states.Conflict):
        states.transition(cid, "QUEUED", "EXTRACTED", round_no=1, actor="test")


# @learn:test-concurrent-decisions
def test_concurrent_decisions_exactly_one_wins():
    """(b) 20 threads race to decide the same case; the conditional write lets exactly one commit."""
    for _ in range(5):
        cid = _case("VALIDATED")
        wins, conflicts = [], []
        barrier = threading.Barrier(20)

        def decide(i):
            barrier.wait()
            to = ["APPROVED", "REJECTED", "IN_REVIEW"][i % 3]
            try:
                states.transition(cid, "VALIDATED", to, round_no=1, actor=f"t{i}")
                wins.append(to)
            except states.Conflict:
                conflicts.append(i)

        ts = [threading.Thread(target=decide, args=(i,)) for i in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert len(wins) == 1 and len(conflicts) == 19
        c = cases.get_case(cid)
        assert c["state"] == wins[0] and len(c["history"]) == 1
        assert len(states.audit_rows(cid)) == 1
# @learn:end test-concurrent-decisions


def test_reconcile_backfills_missing_audit(monkeypatch):
    cid = _case("UPLOADED")
    monkeypatch.setattr(states, "_write_audit", lambda *a, **k: None)  # crash after the DynamoDB commit
    states.transition(cid, "UPLOADED", "QUEUED", round_no=1, actor="test")
    assert states.audit_rows(cid) == []
    monkeypatch.undo()
    assert states.reconcile([cid]) == 1
    assert states.reconcile([cid]) == 0
    assert len(states.audit_rows(cid)) == 1
