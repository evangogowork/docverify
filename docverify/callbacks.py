"""Asynchronous status callbacks: one contract for every platform.

Transitions into a platform-visible state write a row to `callback_outbox` (unique per case, round
and status, so a replayed transition cannot enqueue twice). This dispatcher delivers each row with an
HMAC-SHA256 signature and retries with exponential backoff; receivers dedupe on the event id because
delivery is at-least-once. Run: python -m docverify.callbacks
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import secrets
import time

import httpx

from . import db

NOTIFY_STATES = {"IN_REVIEW", "APPROVED", "REJECTED", "RESUBMIT_REQUESTED", "FAILED"}
MAX_ATTEMPTS = 6
API_VERSION = "v1"


def register_webhook(platform: str, url: str) -> str:
    secret = "whsec_" + secrets.token_urlsafe(24)
    db.execute("INSERT INTO webhooks (platform, url, secret) VALUES (%s,%s,%s)"
               " ON DUPLICATE KEY UPDATE url=VALUES(url), secret=VALUES(secret)", (platform, url, secret))
    return secret


def enqueue(case: dict, status: str, reasons: list[str]) -> None:
    payload = {
        "type": "case.status_changed", "api_version": API_VERSION, "case_id": case["case_id"],
        "account_id": case["account_id"], "platform": case.get("platform"), "round": case["round"],
        "status": status, "reasons": reasons, "occurred_at": time.time(),
    }
    db.execute("INSERT IGNORE INTO callback_outbox (case_id, round_no, status, platform, payload)"
               " VALUES (%s,%s,%s,%s,%s)",
               (case["case_id"], case["round"], status, case.get("platform") or "", json.dumps(payload)))


# @learn:sign
def sign(secret: str, body: bytes, ts: int) -> str:
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify(secret: str, body: bytes, header: str, tolerance: int = 300) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (ValueError, KeyError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False      # stops replay of an old, validly signed request
    return hmac.compare_digest(sign(secret, body, ts), header)
# @learn:end sign


def backoff(attempt: int, base: float) -> float:
    return base * (2 ** (attempt - 1)) * random.uniform(0.8, 1.2)


# @learn:dispatch
def dispatch_once(client: httpx.Client, base: float = 1.0, batch: int = 20) -> int:
    c = db.conn()
    with c.cursor() as cur:
        cur.execute("START TRANSACTION")
        cur.execute("SELECT o.*, w.url, w.secret FROM callback_outbox o JOIN webhooks w ON w.platform=o.platform"
                    " WHERE o.delivered_at IS NULL AND o.dead=0 AND o.next_attempt_at <= NOW(3)"
                    " ORDER BY o.id LIMIT %s FOR UPDATE OF o SKIP LOCKED", (batch,))
        rows = cur.fetchall()
        for r in rows:
            body = json.dumps({**json.loads(r["payload"]), "event_id": f"evt_{r['id']}"}).encode()
            sig = sign(r["secret"], body, int(time.time()))
            attempt = r["attempts"] + 1
            status, err = None, ""
            try:
                resp = client.post(r["url"], content=body, timeout=5, headers={
                    "Content-Type": "application/json", "X-DocVerify-Signature": sig,
                    "X-DocVerify-Event-Id": f"evt_{r['id']}", "X-DocVerify-Api-Version": API_VERSION})
                status = resp.status_code
                ok = 200 <= status < 300
                if not ok:
                    err = resp.text[:200]
            except httpx.HTTPError as e:
                ok, err = False, f"{type(e).__name__}: {e}"[:200]
            cur.execute("INSERT INTO callback_attempts (outbox_id, attempt, http_status, error, signature)"
                        " VALUES (%s,%s,%s,%s,%s)", (r["id"], attempt, status, err, sig))
            if ok:
                cur.execute("UPDATE callback_outbox SET attempts=%s, delivered_at=NOW(3) WHERE id=%s",
                            (attempt, r["id"]))
            else:
                dead = attempt >= MAX_ATTEMPTS
                cur.execute("UPDATE callback_outbox SET attempts=%s, dead=%s, last_error=%s,"
                            " next_attempt_at=NOW(3) + INTERVAL %s MICROSECOND WHERE id=%s",
                            (attempt, int(dead), err, int(backoff(attempt, base) * 1e6), r["id"]))
        cur.execute("COMMIT")
    return len(rows)
# @learn:end dispatch


def main() -> None:
    base = float(os.environ.get("DOCVERIFY_CALLBACK_BACKOFF", "1.0"))
    print(json.dumps({"callbacks": "started", "backoff_base": base}), flush=True)
    with httpx.Client() as client:
        while True:
            try:
                n = dispatch_once(client, base)
            except Exception as e:
                print(json.dumps({"callbacks_error": str(e)[:200]}), flush=True)
                n = 0
            if not n:
                time.sleep(0.3)


if __name__ == "__main__":
    main()
