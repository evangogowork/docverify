# Code as it was before each fix in docs/problems.md. Not imported anywhere.
# ruff: noqa

# @learn:q01-before
def ensure_lambda() -> None:
    s = settings()
    lam = client("lambda")
    code = lambda_pkg.build_zip()
    try:
        lam.get_function(FunctionName=s.lambda_name)
        lam.update_function_code(FunctionName=s.lambda_name, ZipFile=code)   # every bootstrap redeploys
        _wait_lambda(lam, s.lambda_name)
    except ClientError:
        lam.create_function(FunctionName=s.lambda_name, Runtime="python3.11", Handler="handler.handler",
                            Role=ROLE, Code={"ZipFile": code})
# @learn:end q01-before


# @learn:q02-before
def run_once(self, wait: int = 2) -> int:
    r = sqs().receive_message(QueueUrl=queue_url(), MaxNumberOfMessages=10, WaitTimeSeconds=wait,
                              AttributeNames=["All"])
    for m in r.get("Messages", []):
        self.handle(m)          # ten messages, processed one after another
# @learn:end q02-before


# @learn:q03-before
class AliasIndex:
    def add(self, account_id: str, name: str) -> None:
        self._by_name.setdefault(normalize_name(name)[0], set()).add(account_id)   # suffix dropped

    def lookup(self, name: str) -> set[str]:
        return self._by_name.get(normalize_name(name)[0], set())
# @learn:end q03-before


# @learn:q04-before
d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config="--psm 6")   # English model only


def strip_marks(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
# @learn:end q04-before


# @learn:q06-before
for cid in ids:
    c = cases.get_case(cid)
    hist = [(h["round"], h["from"], h["to"]) for h in c["history"]]
    assert len(hist) == len(set(hist)), hist
    assert c["state"] in DONE          # FAILED and wrongly REJECTED both count as "done"
# @learn:end q06-before


# @learn:q07-before
def _ack(self, msg: dict) -> None:
    sqs().delete_message(QueueUrl=queue_url(), ReceiptHandle=msg["ReceiptHandle"])
# @learn:end q07-before


# @learn:q08-before
kwargs = dict(TableName=settings().table, Key={"case_id": {"S": case_id}},
              UpdateExpression="SET " + ", ".join(sets),
              ExpressionAttributeNames=names, ExpressionAttributeValues=values)
new = ddb().update_item(**kwargs)["Attributes"]     # no ConditionExpression: last writer wins
# @learn:end q08-before


# @learn:q09-before
def _retry_later(self, msg: dict) -> None:
    n = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", 1))
    base = float(os.environ.get("DOCVERIFY_RETRY_BASE", "2"))
    delay = int(min(300, base * (2 ** (n - 1))))     # 0.5s base still reaches 64s by the eighth try
    sqs().change_message_visibility(QueueUrl=queue_url(), ReceiptHandle=msg["ReceiptHandle"],
                                    VisibilityTimeout=delay)
# @learn:end q09-before


# @learn:q10-before
def scan_cases(limit: int = 200) -> list[dict]:
    r = ddb().scan(TableName=settings().table, Limit=limit)     # one page: stops at 1 MB
    items = [from_item(i) for i in r.get("Items", [])]
    return sorted(items, key=lambda c: c.get("created_at", 0), reverse=True)
# @learn:end q10-before


# @learn:q11-before
def extract(self, data: bytes, content_type: str) -> Extraction:
    kind = sniff(data, content_type)
    return self.by_type[kind].extract(data, kind)    # field confidence = whatever Tesseract reported
# @learn:end q11-before
