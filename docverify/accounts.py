"""Account records the documents are compared against (MySQL)."""
from __future__ import annotations

import json
import time

from . import db
from .fixtures import ACCOUNTS
from .match import AliasIndex

_cache: tuple[float, AliasIndex] | None = None


def seed() -> None:
    for a in ACCOUNTS:
        db.execute("INSERT INTO accounts (account_id, platform, legal_name, aliases, address) VALUES (%s,%s,%s,%s,%s)"
                   " ON DUPLICATE KEY UPDATE platform=VALUES(platform), legal_name=VALUES(legal_name),"
                   " aliases=VALUES(aliases), address=VALUES(address)",
                   (a["account_id"], a["platform"], a["legal_name"], json.dumps(a["aliases"], ensure_ascii=False),
                    a["address"]))


def _row(r: dict) -> dict:
    return {**r, "aliases": json.loads(r["aliases"]) if isinstance(r["aliases"], str) else r["aliases"]}


def get(account_id: str) -> dict | None:
    rows = db.query("SELECT * FROM accounts WHERE account_id=%s", (account_id,))
    return _row(rows[0]) if rows else None


def all_accounts() -> list[dict]:
    return [_row(r) for r in db.query("SELECT * FROM accounts ORDER BY account_id")]


def alias_index(ttl: float = 30.0) -> AliasIndex:
    global _cache
    if _cache is None or time.time() - _cache[0] > ttl:
        _cache = (time.time(), AliasIndex.from_accounts(all_accounts()))
    return _cache[1]
