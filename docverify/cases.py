"""Case records in DynamoDB. The item is the source of truth for a case's state."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .aws import ddb
from .config import settings


def _ser(v: Any) -> dict:
    if v is None:
        return {"NULL": True}
    if isinstance(v, bool):
        return {"BOOL": v}
    if isinstance(v, (int, float)):
        return {"N": str(v)}
    if isinstance(v, (dict, list)):
        return {"S": json.dumps(v, ensure_ascii=False, sort_keys=True)}
    return {"S": str(v)}


JSON_FIELDS = {"extraction", "validation", "decision_detail", "review", "matches"}


def _native_de(v: dict) -> Any:
    if "M" in v:
        return {k: _native_de(x) for k, x in v["M"].items()}
    if "L" in v:
        return [_native_de(x) for x in v["L"]]
    return _de("", v)


def _de(k: str, v: dict) -> Any:
    if "M" in v or "L" in v:
        return _native_de(v)
    if "NULL" in v:
        return None
    if "BOOL" in v:
        return v["BOOL"]
    if "N" in v:
        n = v["N"]
        return float(n) if "." in n else int(n)
    s = v.get("S")
    if k in JSON_FIELDS and s is not None:
        return json.loads(s)
    return s


def to_item(d: dict) -> dict:
    return {k: _ser(v) for k, v in d.items()}


def from_item(item: dict) -> dict:
    return {k: _de(k, v) for k, v in item.items()}


def new_case_id() -> str:
    return "case_" + uuid.uuid4().hex[:16]


def put_new_case(case: dict) -> None:
    """Create a case. attribute_not_exists makes a retried create a no-op error, not a duplicate."""
    ddb().put_item(
        TableName=settings().table,
        Item=to_item(case),
        ConditionExpression="attribute_not_exists(case_id)",
    )


def get_case(case_id: str) -> dict | None:
    r = ddb().get_item(TableName=settings().table, Key={"case_id": {"S": case_id}}, ConsistentRead=True)
    return from_item(r["Item"]) if "Item" in r else None


def scan_cases(limit: int = 200) -> list[dict]:
    r = ddb().scan(TableName=settings().table, Limit=limit)
    items = [from_item(i) for i in r.get("Items", [])]
    return sorted(items, key=lambda c: c.get("created_at", 0), reverse=True)


def now() -> float:
    return round(time.time(), 3)
