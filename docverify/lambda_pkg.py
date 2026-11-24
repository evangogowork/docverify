"""Build the intake Lambda zip: the handler, the docverify modules it imports, and pymysql."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
MODULES = ["__init__.py", "config.py", "aws.py", "cases.py", "db.py", "states.py"]


def build_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "lambdas/intake/handler.py", "handler.py")
        for m in MODULES:
            z.write(ROOT / "docverify" / m, f"docverify/{m}")
        pkg = Path(pymysql.__file__).parent
        for f in pkg.rglob("*.py"):
            z.write(f, f"pymysql/{f.relative_to(pkg)}")
    return buf.getvalue()
