"""Synthetic business documents: the same spec rendered as a PNG scan or a text-layer PDF.

Used for samples, tests and the evaluation set. Image degradations model what real intake sees:
blur, sensor noise, low resolution, a slightly rotated phone photo.
"""
from __future__ import annotations

import io
import random
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]

TITLES = {
    "business_license": "BUSINESS LICENSE",
    "tax_certificate": "TAX REGISTRATION CERTIFICATE",
    "registration_certificate": "CERTIFICATE OF REGISTRATION",
}


def font_path() -> str:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise RuntimeError("no unicode TTF font found; install fonts-dejavu-core")


def luhn_digit(digits: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def make_registration_number(jurisdiction: str, rng: random.Random) -> str:
    body = "".join(rng.choice("0123456789") for _ in range(8))
    return f"{jurisdiction}-{body}{luhn_digit(body)}"


@dataclass(frozen=True)
class DocSpec:
    doc_type: str
    business_name: str
    registration_number: str
    address: str
    issue_date: str
    expiry_date: str
    issuing_authority: str

    def lines(self) -> list[str]:
        return [
            f"{self.issuing_authority} {TITLES[self.doc_type]}",
            f"Business Name: {self.business_name}",
            f"Registration No: {self.registration_number}",
            f"Address: {self.address}",
            f"Issued: {self.issue_date}",
            f"Expires: {self.expiry_date}",
            f"Issuing Authority: {self.issuing_authority}",
        ]

    def as_dict(self) -> dict:
        return asdict(self)

    def with_(self, **kw) -> "DocSpec":
        return replace(self, **kw)


def render_png(spec: DocSpec, quality: str = "clean", seed: int = 0) -> bytes:
    rng = random.Random(seed)
    w, h = 1400, 820
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(font_path(), 44)
    body_font = ImageFont.truetype(font_path(), 34)
    d.rectangle([20, 20, w - 20, h - 20], outline=0, width=4)
    y = 60
    for i, line in enumerate(spec.lines()):
        d.text((70, y), line, font=title_font if i == 0 else body_font, fill=0)
        y += 100 if i == 0 else 82
    if quality == "blur":
        img = img.filter(ImageFilter.GaussianBlur(radius=2.6))
    elif quality == "noise":
        px = img.load()
        for _ in range(int(w * h * 0.10)):
            x, yy = rng.randrange(w), rng.randrange(h)
            px[x, yy] = rng.choice((0, 255))
    elif quality == "lowres":
        img = img.resize((w // 4, h // 4), Image.BILINEAR).resize((w, h), Image.NEAREST)
    elif quality == "rotate":
        img = img.rotate(rng.uniform(4, 7), expand=True, fillcolor=255)
    elif quality == "faded":
        img = img.point(lambda v: 255 - (255 - v) * 0.18)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def render_pdf(spec: DocSpec) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="Letter")
    pdf.add_page()
    pdf.add_font("uni", "", font_path())
    pdf.set_font("uni", size=16)
    for line in spec.lines():
        pdf.cell(0, 12, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
