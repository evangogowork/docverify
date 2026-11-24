"""Decision policy. The one rule: uncertain AI output never decides account status alone.

- APPROVED only if every schema, rule and confidence check passed AND name and address match.
- REJECTED only on a deterministic rule failure read with high confidence (expired, bad check digit,
  jurisdiction mismatch) — a fact about the document, not a model's guess.
- RESUBMIT_REQUESTED when the document is unreadable (most fields missing).
- Everything else goes to a human, with a risk score that orders the review queue.
"""
from __future__ import annotations

NAME_MATCH = 0.90
ADDRESS_MATCH = 0.85
HARD_FAIL_CONFIDENCE = 0.90
HARD_RULES = {"rule:registration_checksum", "rule:not_expired", "rule:registration_matches_authority",
              "rule:issuing_authority_valid", "rule:issue_before_expiry"}


# @learn:decide
def decide(checks: list[dict], matches: list[dict]) -> dict:
    failed = [c for c in checks if not c["passed"]]
    missing = [c for c in failed if c["name"].startswith("present:")]
    hard = [c for c in failed if c["name"] in HARD_RULES and (c["confidence"] or 0) >= HARD_FAIL_CONFIDENCE]
    by_field = {m["field"]: m for m in matches}
    name_ok = by_field.get("business_name", {}).get("score", 0) >= NAME_MATCH
    addr_ok = by_field.get("address", {}).get("score", 0) >= ADDRESS_MATCH

    risk = 10 + 25 * len([c for c in failed if c["kind"] == "rule"]) \
        + 10 * len([c for c in failed if c["kind"] == "confidence"]) + 8 * len(missing) \
        + 40 * (1 - by_field.get("business_name", {}).get("score", 0)) \
        + 20 * (1 - by_field.get("address", {}).get("score", 0))
    risk = int(min(100, round(risk)))
    reasons = [c["name"] for c in failed] + [f"match:{f}" for f, ok in (("business_name", name_ok),
                                                                           ("address", addr_ok)) if not ok]
    if hard:
        return {"decision": "REJECTED", "risk": risk, "reasons": [c["name"] for c in hard], "automated": True}
    if len(missing) >= 3:
        return {"decision": "RESUBMIT_REQUESTED", "risk": risk, "reasons": ["unreadable"] + reasons,
                "automated": True}
    if not failed and name_ok and addr_ok:
        return {"decision": "APPROVED", "risk": risk, "reasons": [], "automated": True}
    return {"decision": "IN_REVIEW", "risk": risk, "reasons": reasons, "automated": False}
# @learn:end decide
