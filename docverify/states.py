"""The case state machine.

DynamoDB holds the authoritative state. A transition commits only if the item is still in the
`from` state for the same round (ConditionExpression), and the same write appends an entry to the
item's `history` list — so the item carries its own exactly-once transition log. MySQL `audit_log`
is a projection of that history: written right after the commit, and back-filled by `reconcile()`
if the process died in between.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from botocore.exceptions import ClientError

from . import cases, db
from .aws import ddb
from .config import settings

# @learn:state-machine
TRANSITIONS: dict[str, set[str]] = {
    "UPLOADED": {"QUEUED", "FAILED"},
    "QUEUED": {"EXTRACTED", "RESUBMIT_REQUESTED", "FAILED"},
    "EXTRACTED": {"VALIDATED", "FAILED"},
    "VALIDATED": {"APPROVED", "REJECTED", "IN_REVIEW", "RESUBMIT_REQUESTED", "FAILED"},
    "IN_REVIEW": {"APPROVED", "REJECTED", "RESUBMIT_REQUESTED"},
    "RESUBMIT_REQUESTED": {"UPLOADED"},
    "APPROVED": set(),
    "REJECTED": set(),
    "FAILED": set(),
}
TERMINAL = {"APPROVED", "REJECTED", "FAILED"}
# Platform-visible states: entering one writes a callback outbox row.
NOTIFY_STATES = {"IN_REVIEW", "APPROVED", "REJECTED", "RESUBMIT_REQUESTED", "FAILED"}
# States after which this round's automated pipeline has nothing left to do.
PIPELINE_DONE = {"IN_REVIEW", "RESUBMIT_REQUESTED"} | TERMINAL
# @learn:end state-machine


class IllegalTransition(Exception):
    pass


@dataclass
class Conflict(Exception):
    """The conditional write failed: someone else moved the case first."""
    case_id: str
    expected: str
    actual: str | None

    def __str__(self) -> str:
        return f"{self.case_id}: expected {self.expected}, found {self.actual}"


def _native(v):
    if isinstance(v, bool):
        return {"BOOL": v}
    if isinstance(v, (int, float)):
        return {"N": str(v)}
    if v is None:
        return {"NULL": True}
    return {"S": str(v)}


# @learn:transition
def transition(case_id: str, frm: str, to: str, *, round_no: int, actor: str,
               reason: str = "", updates: dict | None = None, detail: dict | None = None,
               condition: tuple[str, dict] | None = None) -> dict:
    """`condition` adds an extra clause, e.g. ("claimed_by = :me", {":me": {"S": "alice"}})."""
    if to not in TRANSITIONS.get(frm, set()):
        raise IllegalTransition(f"{frm} -> {to} is not a legal transition")
    write_id = uuid.uuid4().hex
    ts = cases.now()
    entry = {"M": {"write_id": {"S": write_id}, "from": {"S": frm}, "to": {"S": to},
                   "round": {"N": str(round_no)}, "actor": {"S": actor}, "at": {"N": str(ts)}}}
    names = {"#s": "state", "#r": "round", "#h": "history", "#u": "updated_at", "#v": "version"}
    values = {":to": {"S": to}, ":from": {"S": frm}, ":round": {"N": str(round_no)},
              ":h": {"L": [entry]}, ":empty": {"L": []}, ":ts": {"N": str(ts)},
              ":one": {"N": "1"}, ":zero": {"N": "0"}}
    sets = ["#s = :to", "#h = list_append(if_not_exists(#h, :empty), :h)", "#u = :ts",
            "#v = if_not_exists(#v, :zero) + :one"]
    for i, (k, v) in enumerate((updates or {}).items()):
        names[f"#k{i}"] = k
        values[f":v{i}"] = cases.to_item({k: v})[k]
        sets.append(f"#k{i} = :v{i}")
    kwargs = dict(TableName=settings().table, Key={"case_id": {"S": case_id}},
                  UpdateExpression="SET " + ", ".join(sets),
                  ExpressionAttributeNames=names, ExpressionAttributeValues=values,
                  ReturnValues="ALL_NEW")
    # @learn:conditional-write
    if not settings().unsafe_no_conditional_writes:
        # The whole point: commit only if nobody moved the case since we read it.
        kwargs["ConditionExpression"] = "#s = :from AND #r = :round"
        if condition:
            kwargs["ConditionExpression"] += f" AND ({condition[0]})"
            kwargs["ExpressionAttributeValues"] = {**values, **condition[1]}
    else:
        # Unsafe control: write blindly. Drop the placeholders only the condition used.
        kwargs["ExpressionAttributeValues"] = {k: v for k, v in values.items()
                                               if k not in (":from", ":round")}
        kwargs["ExpressionAttributeNames"] = {k: v for k, v in names.items() if k != "#r"}
    # @learn:end conditional-write
    try:
        new = ddb().update_item(**kwargs)["Attributes"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        cur = cases.get_case(case_id)
        raise Conflict(case_id, frm, cur["state"] if cur else None) from None
    _write_audit(write_id, case_id, round_no, frm, to, actor, reason, detail)
    case = cases.from_item(new)
    if to in NOTIFY_STATES and case.get("platform"):
        from . import callbacks   # lazy: the intake Lambda never reaches a notify state
        callbacks.enqueue(case, to, [r for r in reason.split(",") if r])
    return case
# @learn:end transition


def create(case: dict, *, actor: str) -> None:
    """NEW -> state: the first entry of the history is written together with the item itself."""
    write_id = uuid.uuid4().hex
    entry = {"write_id": write_id, "from": "NEW", "to": case["state"], "round": case["round"],
             "actor": actor, "at": cases.now()}
    item = cases.to_item({k: v for k, v in case.items()})
    item["history"] = {"L": [{"M": {k: _native(v) for k, v in entry.items()}}]}
    item["version"] = {"N": "1"}
    ddb().put_item(TableName=settings().table, Item=item,
                   ConditionExpression="attribute_not_exists(case_id)")
    _write_audit(write_id, case["case_id"], case["round"], "NEW", case["state"], actor, "created", None)


def _write_audit(write_id, case_id, round_no, frm, to, actor, reason, detail) -> None:
    db.execute(
        "INSERT IGNORE INTO audit_log (write_id, case_id, round_no, from_state, to_state, actor, reason, detail)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (write_id, case_id, round_no, frm, to, actor, reason[:255],
         json.dumps(detail, ensure_ascii=False) if detail is not None else None),
    )


def reconcile(case_ids: list[str] | None = None) -> int:
    """Back-fill audit rows for committed transitions whose audit insert never ran (crash window)."""
    filled = 0
    targets = case_ids if case_ids is not None else [
        c["case_id"] for c in cases.scan_cases(1_000_000, fields=["case_id", "updated_at"])
        if cases.now() - float(c.get("updated_at") or 0) < 3600]   # recent writes are where the crash window is
    for cid in targets:
        c = cases.get_case(cid)
        for h in (c or {}).get("history", []) or []:
            filled += db.execute(
                "INSERT IGNORE INTO audit_log (write_id, case_id, round_no, from_state, to_state, actor, reason)"
                " VALUES (%s,%s,%s,%s,%s,%s,'reconciled')",
                (h["write_id"], cid, int(h["round"]), h["from"], h["to"], h["actor"]))
    return filled


def audit_rows(case_id: str) -> list[dict]:
    return db.query("SELECT write_id, round_no, from_state, to_state, actor, reason, detail, created_at"
                    " FROM audit_log WHERE case_id=%s ORDER BY id", (case_id,))
