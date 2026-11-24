"""Evaluation set + release gate.

Generates a labelled corpus (every account x every failure category), runs the real pipeline on it
in-process (OCR, validation, matching, decision — no AWS needed), reports accuracy and incorrect
auto-approvals per category and auto-approval rates per name-origin group, and exits non-zero if
any threshold in evals/thresholds.json is missed. CI runs it as a release gate.

    python -m evals.run            # writes evals/report.json and evals/report.md
    python -m evals.run --matcher exact   # same corpus with naive exact name matching (baseline)
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
import time
from pathlib import Path

from docverify import samples
from docverify.decide import decide
from docverify.documents import render_png
from docverify.extract import CompositeExtractor, UnsupportedFormat
from docverify.fixtures import ACCOUNTS, NAME_GROUP
from docverify.match import AliasIndex, exact_match_name, match_address
from docverify.pipeline import matches_for
from docverify.validate import validate

HERE = Path(__file__).resolve().parent

# How the same business shows up on paper: transliterated, diacritics dropped, order flipped, suffix spelled out.
VARIANT_NAMES = {
    "acct_1001": "ACME WIDGETS, L.L.C.", "acct_1002": "Nguyen Van An Trading Co.", "acct_1003": "Wei Zhang Imports, Inc.",
    "acct_1004": "Mohammed Al Rashid Foods LLC", "acct_1005": "Jose Garcia Construccion LLC",
    "acct_1006": "Okubo Design Studio Limited", "acct_1007": "Oluwaseun Adeyemi Media, Inc.",
    "acct_1008": "Kowalczyk and Sons Plumbing Inc.", "acct_1009": "Priya Raghunathan Consulting, LLC",
    "acct_1010": "Soren Ostergaard Bikes Inc", "acct_1011": "Aleksander Volkov Logistics LLC",
    "acct_1012": "Le Thi Hong Nail Salon LLC",
}

# expected: the set of acceptable decisions. "genuine" docs count toward the auto-match rate.
def corpus():
    for a in ACCOUNTS:
        aid = a["account_id"]
        for kind in ("clean", "pdf"):
            yield {"category": "clean", "kind": kind, "account": a, "expected": {"APPROVED"}, "genuine": True}
        for kind in ("blur", "lowres", "noise", "rotate"):
            yield {"category": "poor_quality", "kind": kind, "account": a,
                   "expected": {"IN_REVIEW", "RESUBMIT_REQUESTED"}, "genuine": True}
        for kind, exp in (("tampered", {"REJECTED"}), ("expired", {"REJECTED"}),
                          ("name_mismatch", {"IN_REVIEW", "REJECTED"}), ("address_mismatch", {"IN_REVIEW", "REJECTED"})):
            yield {"category": "altered", "kind": kind, "account": a, "expected": exp, "genuine": False}
        yield {"category": "unsupported_format", "kind": "unsupported", "account": a,
               "expected": {"RESUBMIT_REQUESTED"}, "genuine": False}
        yield {"category": "demographic", "kind": "variant_name", "account": a, "expected": {"APPROVED"},
               "genuine": True, "name": VARIANT_NAMES[aid]}
    yield from ({"category": "unsupported_format", "kind": k, "account": ACCOUNTS[0], "data": d,
                 "expected": {"RESUBMIT_REQUESTED"}, "genuine": False}
                for k, d in (("gif", b"GIF89a\x01\x00"), ("heic", b"\x00\x00\x00\x18ftypheic"), ("empty_pdf", None)))


def build(item) -> tuple[bytes, str]:
    if "data" in item:
        if item["data"] is None:
            from fpdf import FPDF
            pdf = FPDF(); pdf.add_page()
            return bytes(pdf.output()), "application/pdf"      # PDF without a text layer
        return item["data"], "application/octet-stream"
    if item["kind"] == "variant_name":
        spec = samples.spec_for(item["account"], seed=3, name=item["name"])
        return render_png(spec, "clean", 3), "image/png"
    data, ctype, _ = samples.make(item["kind"], item["account"], seed=1)
    return data, ctype


# @learn:eval-run
def assess_one(item, extractor, index, matcher: str) -> dict:
    data, ctype = build(item)
    try:
        ex = extractor.extract(data, ctype)
    except UnsupportedFormat as e:
        return {"decision": "RESUBMIT_REQUESTED", "reasons": [str(e)[:80]]}
    checks = [c.to_dict() for c in validate(ex, "business_license")]
    if matcher == "exact":
        m = []
        if "business_name" in ex.fields:
            m.append(exact_match_name(ex.fields["business_name"].value, item["account"]).to_dict())
        if "address" in ex.fields:
            m.append(match_address(ex.fields["address"].value, item["account"]).to_dict())
    else:
        m = matches_for(ex, item["account"], index)
    d = decide(checks, m)
    return {"decision": d["decision"], "reasons": d["reasons"][:6]}


def run(matcher: str = "full") -> dict:
    extractor, index = CompositeExtractor(), AliasIndex.from_accounts(ACCOUNTS)
    rows, t0 = [], time.time()
    for item in corpus():
        out = assess_one(item, extractor, index, matcher)
        rows.append({"category": item["category"], "kind": item["kind"], "account_id": item["account"]["account_id"],
                     "group": NAME_GROUP[item["account"]["account_id"]], "genuine": item["genuine"],
                     "expected": sorted(item["expected"]), **out,
                     "correct": out["decision"] in item["expected"],
                     "incorrect_auto_approval": out["decision"] == "APPROVED" and "APPROVED" not in item["expected"]})
    by_cat = collections.defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    summary = {c: {"n": len(rs), "accuracy": round(sum(r["correct"] for r in rs) / len(rs), 4),
                   "incorrect_auto_approvals": sum(r["incorrect_auto_approval"] for r in rs),
                   "auto_approve_rate": round(sum(r["decision"] == "APPROVED" for r in rs) / len(rs), 4),
                   "decisions": dict(collections.Counter(r["decision"] for r in rs)),
                   "errors": [f"{r['account_id']}:{r['kind']}->{r['decision']}" for r in rs if not r["correct"]]}
               for c, rs in by_cat.items()}
    genuine_readable = [r for r in rows if r["category"] in ("clean", "demographic")]
    by_group = collections.defaultdict(list)
    for r in genuine_readable:
        by_group[r["group"]].append(r)
    groups = {g: round(sum(r["decision"] == "APPROVED" for r in rs) / len(rs), 4) for g, rs in sorted(by_group.items())}
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"), "matcher": matcher,
        "seconds": round(time.time() - t0, 1), "n": len(rows), "by_category": summary,
        "auto_match_rate_on_readable_genuine_docs": round(
            sum(r["decision"] == "APPROVED" for r in genuine_readable) / len(genuine_readable), 4),
        "auto_approve_rate_by_name_group": groups,
        "auto_approve_gap_between_name_groups": round(max(groups.values()) - min(groups.values()), 4),
        "incorrect_auto_approvals": sum(r["incorrect_auto_approval"] for r in rows),
        "rows": rows,
    }
# @learn:end eval-run


# @learn:eval-gate
def gate(report: dict, thresholds: dict) -> list[str]:
    failures = []
    for cat, minimum in thresholds["min_accuracy"].items():
        acc = report["by_category"][cat]["accuracy"]
        if acc < minimum:
            failures.append(f"{cat}: accuracy {acc:.3f} < {minimum}")
    if report["incorrect_auto_approvals"] > thresholds["max_incorrect_auto_approvals"]:
        failures.append(f"incorrect auto-approvals {report['incorrect_auto_approvals']}")
    gap = report["auto_approve_gap_between_name_groups"]
    if gap > thresholds["max_auto_approve_gap_between_name_groups"]:
        failures.append(f"auto-approve gap between name groups {gap:.3f}")
    return failures
# @learn:end eval-gate


def to_markdown(r: dict) -> str:
    lines = [f"# Evaluation report ({r['matcher']} matcher, {r['n']} documents, {r['generated_at']})", "",
             "| category | n | decision accuracy | incorrect auto-approvals | auto-approve rate |", "|---|---|---|---|---|"]
    for c, v in r["by_category"].items():
        lines.append(f"| {c} | {v['n']} | {v['accuracy']:.1%} | {v['incorrect_auto_approvals']} | {v['auto_approve_rate']:.1%} |")
    lines += ["", f"Auto-match rate on readable genuine documents: **{r['auto_match_rate_on_readable_genuine_docs']:.1%}**", "",
              "| name group | auto-approve rate |", "|---|---|"]
    lines += [f"| {g} | {v:.0%} |" for g, v in r["auto_approve_rate_by_name_group"].items()]
    lines += ["", "Misses:", ""] + [f"- {c}: {', '.join(v['errors']) or 'none'}" for c, v in r["by_category"].items()]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matcher", choices=["full", "exact"], default="full")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    report = run(a.matcher)
    failures = gate(report, json.loads((HERE / "thresholds.json").read_text()))
    report["gate"] = {"passed": not failures, "failures": failures}
    if not a.no_write:
        suffix = "" if a.matcher == "full" else f".{a.matcher}"
        (HERE / f"report{suffix}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
        (HERE / f"report{suffix}.md").write_text(to_markdown(report))
    print(to_markdown(report))
    print("GATE:", "PASS" if not failures else "FAIL\n  " + "\n  ".join(failures))
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
