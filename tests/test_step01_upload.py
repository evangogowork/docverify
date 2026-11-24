from fastapi.testclient import TestClient

from docverify import cases, states
from docverify.api.main import app
from docverify.aws import s3
from docverify.config import settings

from .helpers import auth_headers


def test_upload_creates_case_and_object():
    c = TestClient(app)
    r = c.post("/v1/cases", data={"account_id": "acct_1001", "doc_type": "business_license"},
               files={"file": ("lic.txt", b"hello", "text/plain")}, headers=auth_headers())
    assert r.status_code == 201, r.text
    body = r.json()
    item = cases.get_case(body["case_id"])
    assert item["state"] in ("UPLOADED", "QUEUED") and item["round"] == 1
    obj = s3().get_object(Bucket=settings().bucket, Key=body["s3_key"])
    assert obj["Body"].read() == b"hello"
    assert obj["Metadata"]["case_id"] == body["case_id"]


def test_rejects_unknown_doc_type():
    c = TestClient(app)
    r = c.post("/v1/cases", data={"account_id": "acct_1001", "doc_type": "selfie"},
               files={"file": ("x.png", b"x", "image/png")}, headers=auth_headers())
    assert r.status_code == 422


def test_upload_writes_creation_audit():
    c = TestClient(app)
    r = c.post("/v1/cases", data={"account_id": "acct_1001", "doc_type": "tax_certificate"},
               files={"file": ("t.txt", b"tax", "text/plain")}, headers=auth_headers())
    rows = states.audit_rows(r.json()["case_id"])
    assert (rows[0]["from_state"], rows[0]["to_state"]) == ("NEW", "UPLOADED")
