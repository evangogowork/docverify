"""Validation of extracted fields: schema checks, deterministic consistency rules, confidence thresholds.

Nothing here decides the case. It produces a list of checks; `decide.py` turns them into a decision
under one rule: AI output that is uncertain never decides account status on its own.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import asdict, dataclass

from .documents import TITLES, luhn_digit
from .extract import FIELDS, Extraction

US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM "
                "NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())

# Minimum confidence at which an extracted field may be relied on without a human looking at it.
CONFIDENCE_THRESHOLDS = {
    "business_name": 0.80, "registration_number": 0.85, "address": 0.75,
    "issue_date": 0.80, "expiry_date": 0.80, "issuing_authority": 0.80,
}
REG_RE = re.compile(r"^([A-Z]{2})-(\d{8})(\d)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today() -> dt.date:
    override = os.environ.get("DOCVERIFY_TODAY")
    return dt.date.fromisoformat(override) if override else dt.date.today()


@dataclass
class Check:
    name: str
    passed: bool
    kind: str          # "schema" | "rule" | "confidence"
    field: str | None
    confidence: float | None
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _date(v: str) -> dt.date | None:
    if not DATE_RE.match(v):
        return None
    try:
        return dt.date.fromisoformat(v)
    except ValueError:
        return None


# @learn:validate
def validate(ex: Extraction, doc_type: str) -> list[Check]:
    f = ex.fields
    checks: list[Check] = []

    def conf(name):
        return f[name].confidence if name in f else None

    # 1. Schema: every field present and well-formed.
    for name in FIELDS:
        checks.append(Check(f"present:{name}", name in f and bool(f[name].value), "schema", name,
                            conf(name), "required field"))
    if "registration_number" in f:
        checks.append(Check("format:registration_number", bool(REG_RE.match(f["registration_number"].value)),
                            "schema", "registration_number", conf("registration_number"), "XX-dddddddd + check digit"))
    for name in ("issue_date", "expiry_date"):
        if name in f:
            checks.append(Check(f"format:{name}", _date(f[name].value) is not None, "schema", name, conf(name),
                                "ISO date"))

    # 2. Deterministic consistency rules.
    reg = REG_RE.match(f["registration_number"].value) if "registration_number" in f else None
    if reg:
        ok = luhn_digit(reg.group(2)) == reg.group(3)
        checks.append(Check("rule:registration_checksum", ok, "rule", "registration_number",
                            conf("registration_number"), "Luhn check digit"))
    if "issuing_authority" in f:
        auth = f["issuing_authority"].value.strip()
        checks.append(Check("rule:issuing_authority_valid", auth in US_STATES, "rule", "issuing_authority",
                            conf("issuing_authority"), "known jurisdiction"))
        if reg:
            checks.append(Check("rule:registration_matches_authority", reg.group(1) == auth, "rule",
                                "registration_number", conf("registration_number"),
                                "registration prefix equals issuing jurisdiction"))
    issued = _date(f["issue_date"].value) if "issue_date" in f else None
    expires = _date(f["expiry_date"].value) if "expiry_date" in f else None
    if expires:
        checks.append(Check("rule:not_expired", expires > today(), "rule", "expiry_date", conf("expiry_date"),
                            f"expires {expires} vs today {today()}"))
    if issued:
        checks.append(Check("rule:issued_not_in_future", issued <= today(), "rule", "issue_date",
                            conf("issue_date"), f"issued {issued}"))
    if issued and expires:
        checks.append(Check("rule:issue_before_expiry", issued < expires, "rule", "expiry_date",
                            min(conf("issue_date"), conf("expiry_date")), "issue < expiry"))
    if ex.title:
        title_ok = TITLES[doc_type].lower() in ex.title.lower()
        checks.append(Check("rule:doc_type_matches_title", title_ok, "rule", None, None,
                            f"title {ex.title!r} vs declared {doc_type}"))

    # 3. Confidence thresholds.
    for name, threshold in CONFIDENCE_THRESHOLDS.items():
        if name in f:
            checks.append(Check(f"confidence:{name}", f[name].confidence >= threshold, "confidence", name,
                                f[name].confidence, f">= {threshold}"))
    return checks
# @learn:end validate
