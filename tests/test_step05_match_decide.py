from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from docverify.api.main import app
from docverify.decide import decide
from docverify.documents import DocSpec, render_pdf, render_png
from docverify.fixtures import ACCOUNTS
from docverify.match import (AliasIndex, levenshtein, match_address, match_name, normalize_name, ratio,
                             token_set_ratio)

from .helpers import drain, upload, wait_state
from .workers import start_worker, stop

A = {a["account_id"]: a for a in ACCOUNTS}
IDX = AliasIndex.from_accounts(ACCOUNTS)
words = st.text(alphabet="abcdefgh ", min_size=0, max_size=12)


@given(words, words)
def test_levenshtein_symmetric_and_bounded(a, b):
    d = levenshtein(a, b)
    assert d == levenshtein(b, a)
    assert abs(len(a) - len(b)) <= d <= max(len(a), len(b))
    assert (d == 0) == (a == b)


@given(words, words, words)
def test_levenshtein_triangle_inequality(a, b, c):
    assert levenshtein(a, c) <= levenshtein(a, b) + levenshtein(b, c)


@given(st.lists(st.sampled_from(["acme", "wei", "zhang", "trading", "foods"]), min_size=1, max_size=5))
def test_token_set_ignores_order_and_duplicates(toks):
    a = " ".join(toks)
    b = " ".join(reversed(toks + toks[:1]))
    assert token_set_ratio(a, b) == 1.0


@given(words, words)
def test_ratios_in_unit_interval(a, b):
    assert 0.0 <= ratio(a, b) <= 1.0 and 0.0 <= token_set_ratio(a, b) <= 1.0


def test_diacritics_abbreviations_and_suffixes():
    assert normalize_name("Nguyễn Văn An Trading Co.") == ("nguyen van an trading", {"company"})
    assert match_name("Wei Zhang Imports, Inc.", A["acct_1003"], IDX).score == 1.0
    assert match_name("Mohammed Al Rashid Foods LLC", A["acct_1004"], IDX).method == "alias"
    # Different legal entity, different business: must NOT clear the auto-match bar.
    assert match_name("Acme Widgets Inc", A["acct_1001"], IDX).score < 0.90
    assert match_name("Apex Widgets LLC", A["acct_1001"], IDX).score < 0.90


def test_address_number_and_zip_are_exact():
    assert match_address("1200 Market St, San Francisco, CA 94102", A["acct_1001"]).score == 1.0
    assert match_address("1210 Market St, San Francisco, CA 94102", A["acct_1001"]).score <= 0.5
    assert match_address("1200 Market St, San Francisco, CA 94103", A["acct_1001"]).score <= 0.5


check = st.fixed_dictionaries({
    "name": st.sampled_from(["present:business_name", "rule:registration_checksum", "rule:not_expired",
                             "confidence:address", "format:issue_date", "rule:doc_type_matches_title"]),
    "passed": st.booleans(), "kind": st.sampled_from(["schema", "rule", "confidence"]),
    "confidence": st.one_of(st.none(), st.floats(0, 1)), "field": st.none(), "detail": st.just(""),
})
match = st.fixed_dictionaries({"field": st.sampled_from(["business_name", "address"]), "score": st.floats(0, 1)})


# @learn:test-policy
@settings(max_examples=500)
@given(st.lists(check, max_size=8), st.lists(match, max_size=2))
def test_policy_never_auto_approves_uncertain_output(checks, matches):
    d = decide(checks, matches)
    if d["decision"] == "APPROVED":
        assert all(c["passed"] for c in checks)
        scores = {m["field"]: m["score"] for m in matches}
        assert scores.get("business_name", 0) >= 0.90 and scores.get("address", 0) >= 0.85
    if d["decision"] == "REJECTED":
        assert any(not c["passed"] and c["name"].startswith("rule:") and (c["confidence"] or 0) >= 0.90
                   for c in checks)
# @learn:end test-policy


SPEC = DocSpec("business_license", "Acme Widgets LLC", "CA-123456782", "1200 Market St, San Francisco, CA 94102",
               "2025-03-01", "2030-03-01", "CA")


def test_worker_end_to_end_decisions():
    drain()
    w = start_worker("w-step05")
    try:
        c = TestClient(app)
        ok = upload(c, "acct_1001", render_png(SPEC), "lic.png", "image/png")
        tampered = upload(c, "acct_1001", render_pdf(SPEC.with_(registration_number="CA-123456783")), "t.pdf",
                          "application/pdf")
        blurry = upload(c, "acct_1001", render_png(SPEC, "lowres"), "b.png", "image/png")
        assert wait_state(ok, {"APPROVED", "REJECTED", "IN_REVIEW"})["state"] == "APPROVED"
        assert wait_state(tampered, {"APPROVED", "REJECTED", "IN_REVIEW"})["state"] == "REJECTED"
        b = wait_state(blurry, {"APPROVED", "REJECTED", "IN_REVIEW", "RESUBMIT_REQUESTED"})
        assert b["state"] in {"IN_REVIEW", "RESUBMIT_REQUESTED"} and b["risk_score"] > 10
    finally:
        stop([w])
