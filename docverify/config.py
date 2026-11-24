"""All configuration comes from the environment; defaults are local-dev placeholders."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    aws_endpoint: str = field(default_factory=lambda: _env("AWS_ENDPOINT_URL", "http://localhost:45661"))
    aws_region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-1"))
    bucket: str = field(default_factory=lambda: _env("DOCVERIFY_BUCKET", "docverify-intake"))
    table: str = field(default_factory=lambda: _env("DOCVERIFY_TABLE", "docverify-cases"))
    queue: str = field(default_factory=lambda: _env("DOCVERIFY_QUEUE", "docverify-cases.fifo"))
    dlq: str = field(default_factory=lambda: _env("DOCVERIFY_DLQ", "docverify-cases-dlq.fifo"))
    lambda_name: str = field(default_factory=lambda: _env("DOCVERIFY_LAMBDA", "docverify-intake"))
    mysql_url: str = field(default_factory=lambda: _env(
        "MYSQL_URL", "mysql://docverify:docverify-dev@127.0.0.1:33501/docverify"))
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL", "redis://127.0.0.1:63501/0"))
    jwt_secret: str = field(default_factory=lambda: _env("DOCVERIFY_JWT_SECRET", "dev-only-change-me"))
    max_receives: int = field(default_factory=lambda: int(_env("DOCVERIFY_MAX_RECEIVES", "4")))
    visibility_timeout: int = field(default_factory=lambda: int(_env("DOCVERIFY_VISIBILITY_TIMEOUT", "20")))
    learn_mode: bool = field(default_factory=lambda: _env("DOCVERIFY_LEARN_MODE", "1") == "1")
    # Failure controls. They exist only so the tests can prove they would catch the bug.
    unsafe_no_conditional_writes: bool = field(
        default_factory=lambda: _env("DOCVERIFY_UNSAFE_NO_CONDITIONAL_WRITES", "0") == "1")
    unsafe_no_dedup: bool = field(default_factory=lambda: _env("DOCVERIFY_UNSAFE_NO_DEDUP", "0") == "1")


def settings() -> Settings:
    # Re-read every call: tests flip env vars between scenarios.
    return Settings()
