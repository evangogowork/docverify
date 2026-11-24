"""Create the AWS resources (idempotent). Run: python -m docverify.bootstrap"""
from __future__ import annotations

import time

from botocore.exceptions import ClientError

import base64
import hashlib
import json
import os

from . import db, lambda_pkg
from .aws import client, ddb, s3, sqs
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


def ensure_queues() -> None:
    s = settings()
    dlq_url = sqs().create_queue(QueueName=s.dlq, Attributes={"FifoQueue": "true"})["QueueUrl"]
    dlq_arn = sqs().get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    attrs = {
        "FifoQueue": "true",
        "VisibilityTimeout": str(s.visibility_timeout),
        # Bounded retries: after max_receives failed attempts the message moves to the DLQ.
        "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": str(s.max_receives)}),
    }
    try:
        url = sqs().create_queue(QueueName=s.queue, Attributes=attrs)["QueueUrl"]
    except ClientError:
        url = sqs().get_queue_url(QueueName=s.queue)["QueueUrl"]
    sqs().set_queue_attributes(QueueUrl=url, Attributes={k: v for k, v in attrs.items() if k != "FifoQueue"})


LAMBDA_ENV = {
    # Inside the Lambda container, LocalStack and MySQL are reached by compose service name.
    "AWS_ENDPOINT_URL": os.environ.get("DOCVERIFY_LAMBDA_AWS_ENDPOINT", "http://localstack:4566"),
    "MYSQL_URL": os.environ.get("DOCVERIFY_LAMBDA_MYSQL_URL",
                                "mysql://docverify:docverify-dev@mysql:3306/docverify"),
}


def ensure_lambda() -> None:
    s = settings()
    lam = client("lambda")
    code = lambda_pkg.build_zip()
    env = {"Variables": {**LAMBDA_ENV, "DOCVERIFY_TABLE": s.table, "DOCVERIFY_QUEUE": s.queue}}
    sha = base64.b64encode(hashlib.sha256(code).digest()).decode()
    try:
        cfg = lam.get_function(FunctionName=s.lambda_name)["Configuration"]
        # Redeploying swaps the runtime container; skip it when nothing changed so in-flight
        # S3 events are not dropped during the swap.
        if cfg.get("CodeSha256") != sha:
            lam.update_function_code(FunctionName=s.lambda_name, ZipFile=code)
            _wait_lambda(lam, s.lambda_name)
        if cfg.get("Environment", {}).get("Variables") != env["Variables"]:
            lam.update_function_configuration(FunctionName=s.lambda_name, Environment=env)
    except ClientError:
        lam.create_function(
            FunctionName=s.lambda_name, Runtime="python3.11", Handler="handler.handler",
            Role="arn:aws:iam::000000000000:role/docverify-intake", Code={"ZipFile": code},
            Timeout=30, MemorySize=512, Environment=env,
        )
    _wait_lambda(lam, s.lambda_name)
    arn = lam.get_function(FunctionName=s.lambda_name)["Configuration"]["FunctionArn"]
    try:
        lam.add_permission(FunctionName=s.lambda_name, StatementId="s3-invoke", Action="lambda:InvokeFunction",
                           Principal="s3.amazonaws.com", SourceArn=f"arn:aws:s3:::{s.bucket}")
    except ClientError:
        pass
    s3().put_bucket_notification_configuration(
        Bucket=s.bucket,
        NotificationConfiguration={"LambdaFunctionConfigurations": [
            {"LambdaFunctionArn": arn, "Events": ["s3:ObjectCreated:*"]}]},
    )


def _wait_lambda(lam, name: str) -> None:
    for _ in range(120):
        cfg = lam.get_function(FunctionName=name)["Configuration"]
        if cfg.get("State") == "Active" and cfg.get("LastUpdateStatus") in (None, "Successful"):
            return
        time.sleep(0.5)
    raise RuntimeError(f"lambda {name} never became active")


def main() -> None:
    ensure_bucket()
    ensure_table()
    db.apply_schema()
    ensure_queues()
    ensure_lambda()
    print("bootstrap ok:", settings().bucket, settings().table)


if __name__ == "__main__":
    main()
