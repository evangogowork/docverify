"""Authentication.

Platforms authenticate as API clients (client_id + secret -> short-lived JWT). Reviewers log in
with a password. Only salted hashes are stored; secrets are shown once, at creation.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .config import settings

PLATFORMS = ("ecommerce", "ads", "live", "payments")
TOKEN_TTL = 3600
_bearer = HTTPBearer(auto_error=False)


def hash_secret(secret: str, salt: str | None = None, iterations: int = 120_000) -> str:
    salt = salt or secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def verify_secret(secret: str, stored: str) -> bool:
    try:
        _, iterations, salt, _ = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_secret(secret, salt, int(iterations)), stored)


def create_client(client_id: str, platform: str, secret: str | None = None) -> str:
    secret = secret or "dvs_" + secrets.token_urlsafe(24)
    db.execute("INSERT INTO api_clients (client_id, platform, secret_hash) VALUES (%s,%s,%s)"
               " ON DUPLICATE KEY UPDATE platform=VALUES(platform), secret_hash=VALUES(secret_hash)",
               (client_id, platform, hash_secret(secret)))
    return secret


def create_reviewer(username: str, password: str, role: str = "reviewer") -> None:
    db.execute("INSERT INTO reviewers (username, password_hash, role) VALUES (%s,%s,%s)"
               " ON DUPLICATE KEY UPDATE password_hash=VALUES(password_hash), role=VALUES(role)",
               (username, hash_secret(password), role))


def issue(sub: str, role: str, platform: str | None = None) -> str:
    now = int(time.time())
    return jwt.encode({"sub": sub, "role": role, "platform": platform, "iat": now, "exp": now + TOKEN_TTL},
                      settings().jwt_secret, algorithm="HS256")


# @learn:auth
def token_for_client(client_id: str, secret: str) -> str:
    rows = db.query("SELECT platform, secret_hash FROM api_clients WHERE client_id=%s", (client_id,))
    if not rows or not verify_secret(secret, rows[0]["secret_hash"]):
        raise HTTPException(401, "invalid client credentials")
    return issue(client_id, "platform", rows[0]["platform"])


def token_for_reviewer(username: str, password: str) -> str:
    rows = db.query("SELECT password_hash, role FROM reviewers WHERE username=%s", (username,))
    if not rows or not verify_secret(password, rows[0]["password_hash"]):
        raise HTTPException(401, "invalid username or password")
    return issue(username, rows[0]["role"])


def principal(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if cred is None:
        raise HTTPException(401, "missing bearer token")
    try:
        return jwt.decode(cred.credentials, settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"invalid token: {e}") from None


def require_platform(p: dict = Depends(principal)) -> dict:
    if p.get("role") != "platform":
        raise HTTPException(403, "platform clients only")
    return p


def require_reviewer(p: dict = Depends(principal)) -> dict:
    if p.get("role") not in ("reviewer", "admin"):
        raise HTTPException(403, "reviewers only")
    return p
# @learn:end auth


def seed_demo() -> dict:
    """Local-dev identities with obvious placeholder secrets. Never enable DOCVERIFY_SEED_DEMO in production."""
    creds = {}
    for p in PLATFORMS:
        creds[p] = create_client(f"{p}-demo", p, f"demo-secret-{p}")
    create_client("learn-demo", "learn", "demo-secret-learn")
    create_reviewer("reviewer", "reviewer-demo-pass", "reviewer")
    create_reviewer("admin", "admin-demo-pass", "admin")
    return creds
