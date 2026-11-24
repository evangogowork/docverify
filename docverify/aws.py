"""boto3 clients pointed at LocalStack (or real AWS if AWS_ENDPOINT_URL is unset upstream)."""
from __future__ import annotations

import functools
import os

import boto3
from botocore.config import Config

from .config import settings


@functools.lru_cache(maxsize=None)
def _client(service: str, endpoint: str, region: str):
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
    return boto3.client(
        service, endpoint_url=endpoint, region_name=region,
        config=Config(retries={"max_attempts": 3, "mode": "standard"},
                      s3={"addressing_style": "path"}),
    )


def client(service: str):
    s = settings()
    return _client(service, s.aws_endpoint, s.aws_region)


def s3():
    return client("s3")


def sqs():
    return client("sqs")


def ddb():
    return client("dynamodb")


def queue_url(name: str | None = None) -> str:
    return sqs().get_queue_url(QueueName=name or settings().queue)["QueueUrl"]
