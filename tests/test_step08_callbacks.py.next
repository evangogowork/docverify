import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
from fastapi.testclient import TestClient

from docverify import callbacks, db
from docverify.api.main import app

from .helpers import auth_headers, drain, upload, wait_state
from .workers import start_worker, stop


def test_signature_roundtrip_and_tamper_and_replay():
    body = b'{"case_id":"case_x","status":"APPROVED"}'
    ts = int(time.time())
    sig = callbacks.sign("whsec_test", body, ts)
    assert callbacks.verify("whsec_test", body, sig)
    assert not callbacks.verify("whsec_other", body, sig)                    # wrong secret
    assert not callbacks.verify("whsec_test", body.replace(b"APPROVED", b"REJECTED"), sig)   # tampered body
    old = callbacks.sign("whsec_test", body, ts - 3600)
    assert not callbacks.verify("whsec_test", body, old)                      # replayed an hour later


class Receiver(BaseHTTPRequestHandler):
    fail_first = 2
    got: list = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Receiver.got.append((self.headers["X-DocVerify-Event-Id"], self.headers["X-DocVerify-Signature"], body))
        if Receiver.fail_first > 0:
            Receiver.fail_first -= 1
            self.send_response(503)
        else:
            self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


def test_outbox_delivers_with_backoff_after_failures():
    srv = HTTPServer(("127.0.0.1", 0), Receiver)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    secret = callbacks.register_webhook("payments", f"http://127.0.0.1:{srv.server_port}/hook")
    case = {"case_id": "case_cbtest%d" % int(time.time() * 1000), "account_id": "acct_1004", "platform": "payments",
            "round": 1}
    callbacks.enqueue(case, "APPROVED", [])
    callbacks.enqueue(case, "APPROVED", [])                 # a replayed transition: unique key, still one row
    rows = db.query("SELECT id FROM callback_outbox WHERE case_id=%s", (case["case_id"],))
    assert len(rows) == 1
    with httpx.Client() as client:
        t0 = time.time()
        while time.time() - t0 < 20:
            callbacks.dispatch_once(client, base=0.2)
            done = db.query("SELECT delivered_at, attempts FROM callback_outbox WHERE id=%s", (rows[0]["id"],))[0]
            if done["delivered_at"]:
                break
            time.sleep(0.05)
    srv.shutdown()
    assert done["delivered_at"] and done["attempts"] == 3                  # 503, 503, 200
    attempts = db.query("SELECT http_status FROM callback_attempts WHERE outbox_id=%s ORDER BY id", (rows[0]["id"],))
    assert [a["http_status"] for a in attempts] == [503, 503, 200]
    mine = [g for g in Receiver.got if json.loads(g[2])["case_id"] == case["case_id"]]
    assert len({g[0] for g in mine}) == 1                                   # same event id on every retry
    assert all(callbacks.verify(secret, g[2], g[1]) for g in mine)


def test_end_to_end_callback_reaches_platform_webhook():
    drain()
    srv = HTTPServer(("127.0.0.1", 0), Receiver)
    Receiver.fail_first, Receiver.got = 0, []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c = TestClient(app)
    eco = auth_headers("ecommerce")
    r = c.put("/v1/webhooks", json={"url": f"http://127.0.0.1:{srv.server_port}/hook"}, headers=eco)
    assert r.status_code == 200 and r.json()["secret"].startswith("whsec_")
    w = start_worker("w-cb")
    try:
        from docverify import accounts, samples
        data, ctype, name = samples.make("pdf", accounts.get("acct_1001"), seed=9)
        cid = upload(c, "acct_1001", data, name, ctype, headers=eco)
        wait_state(cid, {"APPROVED"}, 60)
        with httpx.Client() as client:
            for _ in range(50):
                callbacks.dispatch_once(client, base=0.2)
                if any(json.loads(g[2])["case_id"] == cid for g in Receiver.got):
                    break
                time.sleep(0.1)
        payloads = [json.loads(g[2]) for g in Receiver.got if json.loads(g[2])["case_id"] == cid]
        assert payloads and payloads[0]["status"] == "APPROVED" and payloads[0]["api_version"] == "v1"
        assert c.get(f"/v1/cases/{cid}/callbacks", headers=eco).json()[0]["delivered_at"]
    finally:
        stop([w])
        srv.shutdown()
