"""Field matching: is the business on the document the business on the account?

normalize -> (alias index hit | max(edit-distance ratio, token-set ratio)). Implemented from scratch
so the behaviour is visible and testable; the property tests pin down the metric laws.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass

NAME_ABBREV = {"co": "company", "corp": "corporation", "intl": "international", "mfg": "manufacturing",
               "svc": "services", "svcs": "services", "bros": "brothers", "assoc": "associates",
               "tech": "technology", "dept": "department", "and": "and", "&": "and"}
LEGAL_SUFFIXES = {"llc", "incorporated", "limited", "company", "corporation", "plc", "lp", "llp",
                  "gmbh", "sa", "pte", "pty"}
SUFFIX_CANON = {"inc": "incorporated", "ltd": "limited"}
ADDR_ABBREV = {"st": "street", "ave": "avenue", "av": "avenue", "rd": "road", "blvd": "boulevard",
               "ste": "suite", "fl": "floor", "dr": "drive", "ln": "lane", "hwy": "highway", "pkwy": "parkway",
               "n": "north", "s": "south", "e": "east", "w": "west", "apt": "apartment", "ct": "court"}
# Given-name transliteration variants that edit distance alone scores too low.
NAME_VARIANTS = {"muhammad": "mohammed", "mohamed": "mohammed", "mohammad": "mohammed",
                 "yusuf": "yousef", "youssef": "yousef", "aleksandr": "alexander", "aleksander": "alexander"}


def strip_marks(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def _tokens(s: str) -> list[str]:
    s = strip_marks(s).casefold().replace("&", " and ")
    return [t for t in re.split(r"[^0-9a-z]+", s) if t]


# @learn:normalize
def normalize_name(s: str) -> tuple[str, set[str]]:
    """Returns (core name, legal suffixes). 'Nguyễn Văn An Trading Co.' -> ('nguyen van an trading', {'company'})."""
    toks = [NAME_VARIANTS.get(t, t) for t in (SUFFIX_CANON.get(t, NAME_ABBREV.get(t, t)) for t in _tokens(s))]
    core = [t for t in toks if t not in LEGAL_SUFFIXES]
    suffixes = {t for t in toks if t in LEGAL_SUFFIXES}
    return " ".join(core), suffixes


def normalize_address(s: str) -> str:
    return " ".join(ADDR_ABBREV.get(t, t) for t in _tokens(s))
# @learn:end normalize


# @learn:similarity
def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return 1.0 - levenshtein(a, b) / max(len(a), len(b))


def token_set_ratio(a: str, b: str) -> float:
    """Order- and duplicate-insensitive: 'zhang wei trading' vs 'wei zhang trading' -> 1.0."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 1.0 if ta == tb else 0.0
    inter = " ".join(sorted(ta & tb))
    sa = (inter + " " + " ".join(sorted(ta - tb))).strip()
    sb = (inter + " " + " ".join(sorted(tb - ta))).strip()
    if not inter:
        return ratio(sa, sb)
    return max(ratio(inter, sa), ratio(inter, sb), ratio(sa, sb))
# @learn:end similarity


@dataclass
class MatchResult:
    field: str
    score: float
    method: str
    document_value: str
    account_value: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# @learn:alias-index
class AliasIndex:
    """Hash map from normalized name -> account ids. O(1) exact hits for DBAs and known transliterations."""

    def __init__(self):
        self._by_name: dict[str, set[str]] = {}

    @staticmethod
    def key(name: str) -> str:
        core, suffixes = normalize_name(name)
        return core + "|" + ",".join(sorted(suffixes))   # the legal suffix is part of the identity

    def add(self, account_id: str, name: str) -> None:
        self._by_name.setdefault(self.key(name), set()).add(account_id)

    def lookup(self, name: str) -> set[str]:
        return self._by_name.get(self.key(name), set())

    @classmethod
    def from_accounts(cls, accounts: list[dict]) -> "AliasIndex":
        idx = cls()
        for a in accounts:
            for n in [a["legal_name"], *a.get("aliases", [])]:
                idx.add(a["account_id"], n)
        return idx
# @learn:end alias-index


def match_name(doc_name: str, account: dict, index: AliasIndex) -> MatchResult:
    core_doc, suf_doc = normalize_name(doc_name)
    if account["account_id"] in index.lookup(doc_name):
        return MatchResult("business_name", 1.0, "alias", doc_name, account["legal_name"], "alias index hit")
    best, best_name, method = 0.0, account["legal_name"], "none"
    for cand in [account["legal_name"], *account.get("aliases", [])]:
        core_acc, suf_acc = normalize_name(cand)
        for m, s in (("edit", ratio(core_doc, core_acc)), ("token_set", token_set_ratio(core_doc, core_acc))):
            if suf_doc and suf_acc and not (suf_doc & suf_acc):
                s -= 0.15   # 'Acme LLC' is a different legal entity from 'Acme Inc'
            if s > best:
                best, best_name, method = s, cand, m
    return MatchResult("business_name", round(max(best, 0.0), 3), method, doc_name, best_name)


def match_address(doc_addr: str, account: dict) -> MatchResult:
    a, b = normalize_address(doc_addr), normalize_address(account["address"])
    score = token_set_ratio(a, b)
    num_a, num_b = re.findall(r"\b\d+\b", a), re.findall(r"\b\d+\b", b)
    detail = ""
    # Street number and ZIP must agree exactly; fuzzy text similarity cannot paper over them.
    if num_a[:1] != num_b[:1] or num_a[-1:] != num_b[-1:]:
        score, detail = min(score, 0.5), "street number or ZIP differs"
    return MatchResult("address", round(score, 3), "token_set", doc_addr, account["address"], detail)


def exact_match_name(doc_name: str, account: dict) -> MatchResult:
    """Baseline for the evaluation: case-insensitive string equality."""
    ok = doc_name.strip().lower() == account["legal_name"].strip().lower()
    return MatchResult("business_name", 1.0 if ok else 0.0, "exact", doc_name, account["legal_name"])
