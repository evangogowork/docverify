"""Field extraction behind a replaceable `Extractor` interface.

The default engine is local: Tesseract OCR for scans, the text layer for PDFs. A model-based
extractor (layout model, hosted VLM, ...) only has to return the same `Extraction` shape — every
field carries a confidence, because the validation stage decides what to trust, not the extractor.
"""
from __future__ import annotations

import importlib
import io
import os
import re
import statistics
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Protocol

FIELDS = ["business_name", "registration_number", "address", "issue_date", "expiry_date", "issuing_authority"]

LABELS = {
    "business name": "business_name",
    "registration no": "registration_number",
    "address": "address",
    "issued": "issue_date",
    "expires": "expiry_date",
    "issuing authority": "issuing_authority",
}


class UnsupportedFormat(Exception):
    pass


@dataclass
class FieldValue:
    value: str
    confidence: float
    source: str


@dataclass
class Extraction:
    engine: str
    fields: dict[str, FieldValue] = field(default_factory=dict)
    title: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"engine": self.engine, "title": self.title, "warnings": self.warnings,
                "fields": {k: asdict(v) for k, v in self.fields.items()}}

    @staticmethod
    def from_dict(d: dict) -> "Extraction":
        return Extraction(engine=d["engine"], title=d.get("title", ""), warnings=d.get("warnings", []),
                          fields={k: FieldValue(**v) for k, v in d.get("fields", {}).items()})


# @learn:extractor-protocol
class Extractor(Protocol):
    name: str

    def extract(self, data: bytes, content_type: str) -> Extraction: ...
# @learn:end extractor-protocol


def sniff(data: bytes, content_type: str) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if content_type.startswith("text/"):
        try:
            data.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass
    raise UnsupportedFormat(f"unsupported format (declared {content_type!r}, magic {data[:8]!r})")


def _norm_label(s: str) -> str:
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def _edit(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def parse_lines(lines: list[tuple[str, float]], engine: str) -> Extraction:
    """Map 'Label: value' lines onto fields, tolerating OCR noise in the labels."""
    ex = Extraction(engine=engine)
    if lines:
        ex.title = lines[0][0]
    for text, conf in lines:
        if ":" not in text:
            continue
        label, value = text.split(":", 1)
        nl = _norm_label(label)
        best = min(LABELS, key=lambda L: _edit(nl, L))
        dist = _edit(nl, best)
        if dist > max(2, len(best) // 4):
            continue
        name = LABELS[best]
        value = value.strip()
        label_penalty = 1.0 - 0.05 * dist
        if name not in ex.fields or ex.fields[name].confidence < conf * label_penalty:
            ex.fields[name] = FieldValue(value=value, confidence=round(conf * label_penalty, 3), source=engine)
    missing = [f for f in FIELDS if f not in ex.fields]
    if missing:
        ex.warnings.append("missing fields: " + ", ".join(missing))
    return ex


class TextExtractor:
    name = "text"

    def extract(self, data: bytes, content_type: str) -> Extraction:
        lines = [(ln.strip(), 0.99) for ln in data.decode("utf-8").splitlines() if ln.strip()]
        return parse_lines(lines, self.name)


class PdfTextExtractor:
    name = "pdf-text"

    def extract(self, data: bytes, content_type: str) -> Extraction:
        from pypdf import PdfReader

        text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
        lines = [(ln.strip(), 0.98) for ln in text.splitlines() if ln.strip()]
        if not lines:
            raise UnsupportedFormat("PDF has no text layer")
        return parse_lines(lines, self.name)


def ocr_languages() -> tuple[str, str]:
    """English plus the Latin-script model when it is installed (scripts/fetch_tessdata.sh).
    The English model alone misreads é, ø, ă in names — see docs/problems.md q04."""
    d = Path(os.environ.get("DOCVERIFY_TESSDATA", Path(__file__).resolve().parent.parent / ".runtime" / "tessdata"))
    if (d / "Latin.traineddata").exists() and (d / "eng.traineddata").exists():
        return "eng+Latin", f"--psm 6 --tessdata-dir {d}"
    return "eng", "--psm 6"


# @learn:ocr
class TesseractExtractor:
    """OCR with per-word confidences; a line's confidence is its weakest-quartile word confidence."""
    name = "tesseract"

    def extract(self, data: bytes, content_type: str) -> Extraction:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("L")
        lang, config = ocr_languages()
        d = pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)
        groups: dict[tuple, list[tuple[str, float]]] = {}
        for i, word in enumerate(d["text"]):
            if not word.strip() or float(d["conf"][i]) < 0:
                continue
            key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
            groups.setdefault(key, []).append((word, float(d["conf"][i]) / 100.0))
        lines = []
        for key in sorted(groups):
            words = groups[key]
            confs = sorted(c for _, c in words)
            q = confs[: max(1, len(confs) // 4)]
            lines.append((" ".join(w for w, _ in words), round(statistics.mean(q), 3)))
        return parse_lines(lines, self.name)
# @learn:end ocr


# Tesseract's confidence describes the words it read, not the image: on a blurred sample, Tesseract 5.5.4
# reads the fields it finds at 0.73-0.95, and blurred scans only failed here because some fields came back
# missing. Ubuntu's Tesseract read all six fields above threshold and the eval gate caught two blurred scans
# auto-approved in CI. So the image itself is measured: variance of the Laplacian, a sharpness score that
# does not depend on the OCR engine. The synthetic scans measure ~750 clean, 600-700 low-res or rotated,
# ~70 blurred. A heuristic tuned on these samples, not a general image-quality model.
# @learn:sharpness
SHARPNESS_MIN = 200.0
BLURRED_CONFIDENCE_CAP = 0.5


def image_sharpness(data: bytes) -> float:
    from PIL import Image, ImageFilter, ImageStat

    gray = Image.open(io.BytesIO(data)).convert("L")
    lap = gray.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128))
    return ImageStat.Stat(lap).var[0]


def cap_if_blurred(ex: Extraction, data: bytes) -> Extraction:
    sharpness = image_sharpness(data)
    if sharpness < SHARPNESS_MIN:
        ex.warnings.append(f"image too blurry: sharpness {sharpness:.0f} < {SHARPNESS_MIN:.0f}")
        for f in ex.fields.values():
            f.confidence = min(f.confidence, BLURRED_CONFIDENCE_CAP)
    return ex
# @learn:end sharpness


class CompositeExtractor:
    name = "composite"

    def __init__(self):
        self.by_type = {"text/plain": TextExtractor(), "application/pdf": PdfTextExtractor(),
                        "image/png": TesseractExtractor(), "image/jpeg": TesseractExtractor()}

    def extract(self, data: bytes, content_type: str) -> Extraction:
        kind = sniff(data, content_type)
        ex = self.by_type[kind].extract(data, kind)
        return cap_if_blurred(ex, data) if kind.startswith("image/") else ex


def get_extractor() -> Extractor:
    """DOCVERIFY_EXTRACTOR=package.module:ClassName swaps in another engine (e.g. a model)."""
    spec = os.environ.get("DOCVERIFY_EXTRACTOR")
    if spec:
        mod, cls = spec.split(":")
        return getattr(importlib.import_module(mod), cls)()
    return CompositeExtractor()
