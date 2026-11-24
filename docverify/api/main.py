"""Versioned REST API. Every route lives under /v1: four platforms share this one contract."""
from __future__ import annotations

import hashlib
import threading
import time

from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from .. import accounts, auth, callbacks, cases, db, samples, states
from ..aws import ddb, s3
from ..config import settings
from ..review import ReviewQueue

app = FastAPI(title="docverify", version="1")

DOC_TYPES = {"business_license", "tax_certificate", "registration_certificate"}
CLAIM_TTL = 15 * 60
review_queue = ReviewQueue()


# ---- auth ---------------------------------------------------------------------------------------
class ClientCreds(BaseModel):
    client_id: str
    client_secret: str


class Login(BaseModel):
    username: str
    password: str


@app.post("/v1/auth/token")
def token(body: ClientCreds):
    return {"access_token": auth.token_for_client(body.client_id, body.client_secret), "token_type": "bearer",
            "expires_in": auth.TOKEN_TTL}


@app.post("/v1/auth/login")
def login(body: Login):
    return {"access_token": auth.token_for_reviewer(body.username, body.password), "token_type": "bearer",
            "expires_in": auth.TOKEN_TTL}


@app.get("/v1/me")
def me(p: dict = Depends(auth.principal)):
    return p


@app.get("/v1/health")
def health():
    return {"ok": True}


# ---- access control -----------------------------------------------------------------------------
def _visible(case: dict | None, p: dict) -> dict:
    if case is None:
        raise HTTPException(404, "no such case")
    if p["role"] == "platform" and case.get("platform") != p["platform"]:
        raise HTTPException(404, "no such case")        # do not reveal other platforms' cases
    return case


def _account_for(p: dict, account_id: str) -> dict:
    acct = accounts.get(account_id)
    if acct is None:
        raise HTTPException(404, f"unknown account {account_id}")
    if p["platform"] != "learn" and acct["platform"] != p["platform"]:
        raise HTTPException(403, "account belongs to another platform")
    return acct


@app.get("/v1/accounts")
def list_accounts(p: dict = Depends(auth.principal)):
    rows = accounts.all_accounts()
    if p["role"] == "platform" and p["platform"] != "learn":
        rows = [a for a in rows if a["platform"] == p["platform"]]
    return rows


# ---- cases --------------------------------------------------------------------------------------
def _store(case_id: str, account_id: str, round_no: int, filename: str, body: bytes, ctype: str) -> str:
    key = f"{account_id}/{case_id}/r{round_no}/{filename}"
    s3().put_object(Bucket=settings().bucket, Key=key, Body=body, ContentType=ctype,
                    Metadata={"case_id": case_id, "account_id": account_id, "round": str(round_no)})
    return key


def create_case(p: dict, account_id: str, doc_type: str, filename: str, body: bytes, ctype: str) -> dict:
    # @learn:upload
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {sorted(DOC_TYPES)}")
    if not body:
        raise HTTPException(422, "empty file")
    _account_for(p, account_id)
    case_id = cases.new_case_id()
    key = f"{account_id}/{case_id}/r1/{filename}"
    case = {
        "case_id": case_id, "account_id": account_id, "doc_type": doc_type, "platform": p["platform"],
        "submitted_by": p["sub"], "state": "UPLOADED", "round": 1, "s3_key": key,
        "sha256": hashlib.sha256(body).hexdigest(), "content_type": ctype or "application/octet-stream",
        "created_at": cases.now(), "updated_at": cases.now(),
    }
    states.create(case, actor=f"api:{p['sub']}")           # DynamoDB first: NEW -> UPLOADED
    _store(case_id, account_id, 1, filename, body, case["content_type"])   # then S3, which fires the Lambda
    return {"case_id": case_id, "state": "UPLOADED", "s3_key": key, "round": 1}
    # @learn:end upload


@app.post("/v1/cases", status_code=201)
async def post_case(account_id: str = Form(...), doc_type: str = Form(...), file: UploadFile = File(...),
                    p: dict = Depends(auth.require_platform)):
    return create_case(p, account_id, doc_type, file.filename or "document", await file.read(),
                       file.content_type or "application/octet-stream")


@app.get("/v1/cases")
def list_cases(p: dict = Depends(auth.principal)):
    items = cases.scan_cases(500, fields=["case_id", "platform", "account_id", "doc_type", "round", "state",
                                          "risk_score", "updated_at", "created_at"])
    if p["role"] == "platform":
        items = [c for c in items if c.get("platform") == p["platform"]]
    keep = ("case_id", "platform", "account_id", "doc_type", "round", "state", "risk_score", "updated_at", "created_at")
    return [{k: c.get(k) for k in keep} for c in items]


@app.get("/v1/cases/{case_id}")
def get_case(case_id: str, p: dict = Depends(auth.principal)):
    return _visible(cases.get_case(case_id), p)


@app.get("/v1/cases/{case_id}/audit")
def get_audit(case_id: str, p: dict = Depends(auth.principal)):
    _visible(cases.get_case(case_id), p)
    return states.audit_rows(case_id)


@app.get("/v1/cases/{case_id}/document")
def get_document(case_id: str, p: dict = Depends(auth.principal)):
    c = _visible(cases.get_case(case_id), p)
    obj = s3().get_object(Bucket=settings().bucket, Key=c["s3_key"])
    return Response(obj["Body"].read(), media_type=c.get("content_type") or "application/octet-stream",
                    headers={"Cache-Control": "private, no-store"})


# @learn:resubmit
@app.post("/v1/cases/{case_id}/resubmit")
async def resubmit(case_id: str, file: UploadFile = File(...), p: dict = Depends(auth.require_platform)):
    c = _visible(cases.get_case(case_id), p)
    if c["state"] != "RESUBMIT_REQUESTED":
        raise HTTPException(409, f"case is {c['state']}, not RESUBMIT_REQUESTED")
    body = await file.read()
    new_round = int(c["round"]) + 1
    ctype = file.content_type or "application/octet-stream"
    key = f"{c['account_id']}/{case_id}/r{new_round}/{file.filename}"
    try:
        states.transition(case_id, "RESUBMIT_REQUESTED", "UPLOADED", round_no=int(c["round"]), actor=f"api:{p['sub']}",
                          reason="resubmitted", updates={
                              "round": new_round, "s3_key": key, "sha256": hashlib.sha256(body).hexdigest(),
                              "content_type": ctype, "extraction": None, "validation": None, "matches": None,
                              "decision_detail": None, "risk_score": None, "claimed_by": None})
    except states.Conflict as e:
        raise HTTPException(409, str(e)) from None
    _store(case_id, c["account_id"], new_round, file.filename or "document", body, ctype)
    return {"case_id": case_id, "state": "UPLOADED", "round": new_round}
# @learn:end resubmit


# ---- callbacks ----------------------------------------------------------------------------------
class Webhook(BaseModel):
    url: str


@app.put("/v1/webhooks")
def put_webhook(body: Webhook, p: dict = Depends(auth.require_platform)):
    """Register the platform's callback URL. The signing secret is returned once, here."""
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(422, "url must be http(s)")
    return {"platform": p["platform"], "url": body.url, "secret": callbacks.register_webhook(p["platform"], body.url)}


@app.get("/v1/cases/{case_id}/callbacks")
def get_callbacks(case_id: str, p: dict = Depends(auth.principal)):
    _visible(cases.get_case(case_id), p)
    return db.query("SELECT id, round_no, status, attempts, delivered_at, dead, last_error FROM callback_outbox"
                    " WHERE case_id=%s ORDER BY id", (case_id,))


# ---- human review -------------------------------------------------------------------------------
def refresh_review_queue() -> None:
    now = time.time()
    in_review = {c["case_id"]: c for c in cases.scan_cases(
        100_000, state="IN_REVIEW",
        fields=["case_id", "state", "claimed_by", "claim_expires", "risk_score", "review_enqueued_at", "updated_at", "created_at"])}
    for cid, c in in_review.items():
        claimed = c.get("claimed_by") and float(c.get("claim_expires") or 0) > now
        if claimed:
            review_queue.remove(cid)
        else:
            review_queue.push(cid, float(c.get("risk_score") or 0), float(c.get("review_enqueued_at") or c["updated_at"]))
    for item in review_queue.peek_order():
        if item["case_id"] not in in_review:
            review_queue.remove(item["case_id"])


def _refresher() -> None:
    while True:
        try:
            refresh_review_queue()
        except Exception as e:  # LocalStack restarting, etc.
            print("review refresh failed:", e, flush=True)
        time.sleep(1.0)


@app.on_event("startup")
def _start_background() -> None:
    threading.Thread(target=_refresher, daemon=True).start()


@app.get("/v1/review/queue")
def get_queue(p: dict = Depends(auth.require_reviewer)):
    refresh_review_queue()
    out = []
    now = time.time()
    for item in review_queue.peek_order(now):
        c = cases.get_case(item["case_id"])
        if c:
            out.append({**item, "account_id": c["account_id"], "risk_score": c.get("risk_score"),
                        "waited": now - float(c.get("review_enqueued_at") or c["updated_at"]),
                        "reasons": (c.get("decision_detail") or {}).get("reasons", [])})
    return {"aging_seconds_per_point": review_queue.aging, "items": out}


# @learn:claim
@app.post("/v1/review/claim")
def claim(p: dict = Depends(auth.require_reviewer)):
    refresh_review_queue()
    while (cid := review_queue.pop()) is not None:
        now = time.time()
        try:
            ddb().update_item(
                TableName=settings().table, Key={"case_id": {"S": cid}},
                UpdateExpression="SET claimed_by = :me, claim_expires = :exp",
                ConditionExpression="#s = :review AND (attribute_not_exists(claimed_by) OR claimed_by = :null"
                                    " OR claim_expires < :now)",
                ExpressionAttributeNames={"#s": "state"},
                ExpressionAttributeValues={":me": {"S": p["sub"]}, ":exp": {"N": str(now + CLAIM_TTL)},
                                           ":review": {"S": "IN_REVIEW"}, ":null": {"NULL": True},
                                           ":now": {"N": str(now)}})
            return cases.get_case(cid)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            # someone else claimed or decided it between our pop and our write: try the next one
    raise HTTPException(404, "review queue is empty")
# @learn:end claim


@app.get("/v1/review/cases/{case_id}")
def review_case(case_id: str, p: dict = Depends(auth.require_reviewer)):
    return _visible(cases.get_case(case_id), p)


class Decision(BaseModel):
    decision: str
    reason: str = ""
    notes: str = ""


def decide_review(case_id: str, reviewer: str, body: Decision, require_claim: bool = True) -> dict:
    if body.decision not in ("APPROVED", "REJECTED", "RESUBMIT_REQUESTED"):
        raise HTTPException(422, "decision must be APPROVED, REJECTED or RESUBMIT_REQUESTED")
    c = cases.get_case(case_id)
    if c is None:
        raise HTTPException(404, "no such case")
    cond = ("claimed_by = :me", {":me": {"S": reviewer}}) if require_claim else None
    try:
        new = states.transition(case_id, "IN_REVIEW", body.decision, round_no=int(c["round"]),
                                actor=f"reviewer:{reviewer}", reason=body.reason or "reviewed",
                                updates={"review": {"reviewer": reviewer, "decision": body.decision,
                                                    "reason": body.reason, "notes": body.notes, "at": cases.now()},
                                         "claimed_by": None},
                                condition=cond)
    except states.Conflict as e:
        raise HTTPException(409, f"not claimed by you or already decided ({e})") from None
    review_queue.remove(case_id)
    return new


@app.post("/v1/review/cases/{case_id}/decision")
def post_decision(case_id: str, body: Decision, p: dict = Depends(auth.require_reviewer)):
    return decide_review(case_id, p["sub"], body)


# ---- dev conveniences ---------------------------------------------------------------------------
@app.get("/v1/samples/{kind}")
def sample(kind: str, account_id: str, doc_type: str = "business_license"):
    if not settings().learn_mode:
        raise HTTPException(404, "samples are only served in learn/dev mode")
    acct = accounts.get(account_id)
    if acct is None or kind not in samples.KINDS:
        raise HTTPException(404, "unknown account or sample kind")
    data, ctype, name = samples.make(kind, acct, doc_type, seed=int(time.time()))
    return Response(data, media_type=ctype, headers={"X-Filename": name, "Access-Control-Expose-Headers": "X-Filename"})
