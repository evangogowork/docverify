from fastapi.testclient import TestClient

from docverify import cases
from docverify.api.main import app
from docverify.aws import s3
from docverify.config import settings


def test_upload_creates_case_and_object():
    c = TestClient(app)
    r = c.post("/v1/cases", data={"account_id": "acct_1", "doc_type": "business_license"},
               files={"file": ("lic.txt", b"hello", "text/plain")})
    assert r.status_code == 201, r.text
    body = r.json()
    item = cases.get_case(body["case_id"])
    assert item["state"] == "UPLOADED" and item["round"] == 1
    obj = s3().get_object(Bucket=settings().bucket, Key=body["s3_key"])
    assert obj["Body"].read() == b"hello"
    assert obj["Metadata"]["case_id"] == body["case_id"]


def test_rejects_unknown_doc_type():
    c = TestClient(app)
    r = c.post("/v1/cases", data={"account_id": "a", "doc_type": "selfie"},
               files={"file": ("x.png", b"x", "image/png")})
    assert r.status_code == 422


def test_upload_writes_creation_audit():
    from docverify import states
    c = TestClient(app)
    r = c.post("/v1/cases", data={"account_id": "acct_1", "doc_type": "tax_certificate"},
               files={"file": ("t.txt", b"tax", "text/plain")})
    rows = states.audit_rows(r.json()["case_id"])
    assert [(x["from_state"], x["to_state"]) for x in rows] == [("NEW", "UPLOADED")]
