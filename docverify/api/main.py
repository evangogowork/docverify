"""Versioned REST API. Every route lives under /v1 so the contract can evolve without breaking platforms."""
from __future__ import annotations

import hashlib

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .. import cases
from ..aws import s3
from ..config import settings

app = FastAPI(title="docverify", version="1")

DOC_TYPES = {"business_license", "tax_certificate", "registration_certificate"}


@app.get("/v1/health")
def health():
    return {"ok": True}


# @learn:upload
@app.post("/v1/cases", status_code=201)
async def create_case(
    account_id: str = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
):
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {sorted(DOC_TYPES)}")
    body = await file.read()
    if not body:
        raise HTTPException(422, "empty file")
    case_id = cases.new_case_id()
    key = f"{account_id}/{case_id}/r1/{file.filename}"
    case = {
        "case_id": case_id, "account_id": account_id, "doc_type": doc_type,
        "state": "UPLOADED", "round": 1, "s3_key": key, "sha256": hashlib.sha256(body).hexdigest(),
        "content_type": file.content_type or "application/octet-stream",
        "created_at": cases.now(), "updated_at": cases.now(),
    }
    cases.put_new_case(case)
    s3().put_object(Bucket=settings().bucket, Key=key, Body=body, ContentType=case["content_type"],
                    Metadata={"case_id": case_id, "account_id": account_id, "round": "1"})
    return {"case_id": case_id, "state": "UPLOADED", "s3_key": key}
# @learn:end upload


@app.get("/v1/cases/{case_id}")
def get_case(case_id: str):
    c = cases.get_case(case_id)
    if not c:
        raise HTTPException(404, "no such case")
    return c
