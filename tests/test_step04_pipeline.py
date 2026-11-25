import pytest
from fastapi.testclient import TestClient

from docverify.api.main import app
from docverify.documents import DocSpec, render_pdf, render_png
from docverify.extract import CompositeExtractor, UnsupportedFormat
from docverify.validate import validate

from .helpers import drain, upload, wait_state
from .workers import start_worker, stop

SPEC = DocSpec("business_license", "Acme Widgets LLC", "CA-123456782", "1200 Market St, San Francisco, CA 94102",
               "2025-03-01", "2030-03-01", "CA")


def failed(checks):
    return sorted(c.name for c in checks if not c.passed)


def test_clean_scan_passes_every_check():
    ex = CompositeExtractor().extract(render_png(SPEC), "image/png")
    assert ex.fields["registration_number"].value == "CA-123456782"
    assert failed(validate(ex, "business_license")) == []


def test_pdf_text_layer():
    ex = CompositeExtractor().extract(render_pdf(SPEC), "application/pdf")
    assert ex.fields["business_name"].value == "Acme Widgets LLC"


def test_blurred_scan_fails_confidence_not_rules():
    ex = CompositeExtractor().extract(render_png(SPEC, "lowres"), "image/png")
    names = failed(validate(ex, "business_license"))
    assert any(n.startswith("confidence:") for n in names)


def test_blurred_scan_goes_to_review_even_if_ocr_is_confident(monkeypatch):
    """Ubuntu's Tesseract read every field of a blurred scan above threshold; the eval gate caught it in CI.
    Stand in for that build: an OCR that reads all six fields correctly at 0.99, whatever the image."""
    from docverify import extract

    def perfect_reader(self, data, content_type):
        ex = extract.PdfTextExtractor().extract(render_pdf(SPEC), "application/pdf")
        for f in ex.fields.values():
            f.confidence, f.source = 0.99, "tesseract"
        return ex

    monkeypatch.setattr(extract.TesseractExtractor, "extract", perfect_reader)
    sharp = CompositeExtractor().extract(render_png(SPEC), "image/png")
    assert sharp.warnings == [] and failed(validate(sharp, "business_license")) == []   # would auto-approve
    blurred = CompositeExtractor().extract(render_png(SPEC, "blur"), "image/png")
    assert any(w.startswith("image too blurry") for w in blurred.warnings)
    names = failed(validate(blurred, "business_license"))
    assert names and all(n.startswith("confidence:") for n in names), names   # review, not a rule rejection


def test_tampered_check_digit_fails_checksum():
    ex = CompositeExtractor().extract(render_pdf(SPEC.with_(registration_number="CA-123456783")), "application/pdf")
    assert "rule:registration_checksum" in failed(validate(ex, "business_license"))


def test_expired_document():
    ex = CompositeExtractor().extract(render_pdf(SPEC.with_(expiry_date="2024-01-01")), "application/pdf")
    assert "rule:not_expired" in failed(validate(ex, "business_license"))


def test_unsupported_format():
    with pytest.raises(UnsupportedFormat):
        CompositeExtractor().extract(b"PK\x03\x04docx", "application/vnd.openxmlformats")


def test_worker_drives_case_to_validated():
    drain()
    w = start_worker("w-step04")
    try:
        c = TestClient(app)
        ok = upload(c, "acct_1001", render_png(SPEC), "lic.png", "image/png")
        bad = upload(c, "acct_1002", b"PK\x03\x04docx", "lic.docx", "application/octet-stream")
        case = wait_state(ok, {"VALIDATED", "APPROVED", "IN_REVIEW", "REJECTED"})
        assert case["extraction"]["fields"]["business_name"]["value"] == "Acme Widgets LLC"
        assert all(ch["passed"] for ch in case["validation"])
        assert wait_state(bad, {"RESUBMIT_REQUESTED"})["state"] == "RESUBMIT_REQUESTED"
    finally:
        stop([w])
