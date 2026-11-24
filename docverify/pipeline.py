"""The pure part of the pipeline: (extraction, doc type, account) -> checks, matches, decision.

The worker wraps it in conditional state transitions; the evaluation harness calls it directly.
"""
from __future__ import annotations

from .decide import decide
from .extract import Extraction
from .match import AliasIndex, match_address, match_name
from .validate import validate


def matches_for(ex: Extraction, account: dict | None, index: AliasIndex) -> list[dict]:
    if account is None:
        return []
    out = []
    if "business_name" in ex.fields:
        out.append(match_name(ex.fields["business_name"].value, account, index).to_dict())
    if "address" in ex.fields:
        out.append(match_address(ex.fields["address"].value, account).to_dict())
    return out


def assess(ex: Extraction, doc_type: str, account: dict | None, index: AliasIndex) -> dict:
    checks = [c.to_dict() for c in validate(ex, doc_type)]
    matches = matches_for(ex, account, index)
    decision = decide(checks, matches)
    if account is None:
        decision = {**decision, "decision": "IN_REVIEW", "automated": False,
                    "reasons": ["unknown_account", *decision["reasons"]]}
    return {"checks": checks, "matches": matches, "decision": decision}
