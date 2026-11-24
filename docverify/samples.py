"""Sample documents for an account: a correct one, and each way a real submission goes wrong."""
from __future__ import annotations

import datetime as dt
import random
import re
import zipfile
import io

from .documents import DocSpec, make_registration_number, render_pdf, render_png
from .validate import today

KINDS = ["clean", "pdf", "blur", "lowres", "noise", "rotate", "tampered", "expired", "name_mismatch",
         "address_mismatch", "unsupported"]


def jurisdiction(address: str) -> str:
    m = re.search(r",\s*([A-Z]{2})\s+\d{5}", address)
    return m.group(1) if m else "CA"


def spec_for(account: dict, doc_type: str = "business_license", seed: int = 0, name: str | None = None) -> DocSpec:
    rng = random.Random(f"{account['account_id']}:{doc_type}:{seed}")
    jur = jurisdiction(account["address"])
    t = today()
    return DocSpec(doc_type=doc_type, business_name=name or account["legal_name"],
                   registration_number=make_registration_number(jur, rng), address=account["address"],
                   issue_date=(t - dt.timedelta(days=rng.randint(60, 900))).isoformat(),
                   expiry_date=(t + dt.timedelta(days=rng.randint(200, 1500))).isoformat(),
                   issuing_authority=jur)


def fake_docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document>business license</w:document>")
    return buf.getvalue()


def make(kind: str, account: dict, doc_type: str = "business_license", seed: int = 0) -> tuple[bytes, str, str]:
    """Returns (bytes, content_type, filename)."""
    s = spec_for(account, doc_type, seed)
    if kind in ("clean", "blur", "lowres", "noise", "rotate"):
        return render_png(s, kind, seed), "image/png", f"{kind}.png"
    if kind == "pdf":
        return render_pdf(s), "application/pdf", "document.pdf"
    if kind == "tampered":
        reg = s.registration_number
        bad = reg[:-1] + str((int(reg[-1]) + 3) % 10)          # altered check digit
        return render_pdf(s.with_(registration_number=bad)), "application/pdf", "tampered.pdf"
    if kind == "expired":
        return render_pdf(s.with_(expiry_date=(today() - dt.timedelta(days=30)).isoformat())), "application/pdf", "expired.pdf"
    if kind == "name_mismatch":
        return render_pdf(s.with_(business_name="Northwind Holdings LLC")), "application/pdf", "other.pdf"
    if kind == "address_mismatch":
        return render_pdf(s.with_(address="77 Unrelated Road, Reno, NV 89501")), "application/pdf", "addr.pdf"
    if kind == "unsupported":
        return fake_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "license.docx"
    raise KeyError(kind)
