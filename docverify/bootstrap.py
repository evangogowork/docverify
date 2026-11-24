"""Create the AWS resources (idempotent). Run: python -m docverify.bootstrap"""
from __future__ import annotations

import time

from botocore.exceptions import ClientError

from .aws import ddb, s3
from .config import settings


def ensure_bucket() -> None:
    s = settings()
    try:
        s3().head_bucket(Bucket=s.bucket)
    except ClientError:
        s3().create_bucket(Bucket=s.bucket)


def ensure_table() -> None:
    s = settings()
    try:
        ddb().describe_table(TableName=s.table)
        return
    except ClientError:
        pass
    ddb().create_table(
        TableName=s.table,
        KeySchema=[{"AttributeName": "case_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "case_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    for _ in range(50):
        if ddb().describe_table(TableName=s.table)["Table"]["TableStatus"] == "ACTIVE":
            return
        time.sleep(0.2)


def main() -> None:
    ensure_bucket()
    ensure_table()
    print("bootstrap ok:", settings().bucket, settings().table)


if __name__ == "__main__":
    main()
