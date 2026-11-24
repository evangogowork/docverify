"""MySQL access (audit, accounts, outbox). One connection per thread, autocommit."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import pymysql
import pymysql.cursors

from .config import settings

_local = threading.local()


def _connect():
    u = urlparse(settings().mysql_url)
    return pymysql.connect(
        host=u.hostname, port=u.port or 3306, user=u.username, password=u.password,
        database=u.path.lstrip("/"), autocommit=True, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, connect_timeout=5,
    )


def conn():
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "url", None) != settings().mysql_url:
        c = _local.conn = _connect()
        _local.url = settings().mysql_url
    else:
        try:
            c.ping(reconnect=False)
        except pymysql.err.Error:
            c = _local.conn = _connect()
    return c


def query(sql: str, args=None) -> list[dict]:
    with conn().cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def execute(sql: str, args=None) -> int:
    with conn().cursor() as cur:
        return cur.execute(sql, args)


def apply_schema(path: Path | None = None, retries: int = 30) -> None:
    path = path or Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
    sql = "\n".join(l for l in path.read_text().splitlines() if not l.strip().startswith("--"))
    for attempt in range(retries):
        try:
            for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
                execute(stmt)
            return
        except pymysql.err.OperationalError:
            if attempt == retries - 1:
                raise
            time.sleep(1)
