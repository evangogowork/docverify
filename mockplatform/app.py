"""A stand-in for the four business platforms: registers webhooks, verifies signatures, records callbacks.

Run: uvicorn mockplatform.app:app --port 8511
It logs in to the docverify API with the demo client for each platform and registers
http://<self>/hooks/<platform>; the API answers with the signing secret, which is kept in memory.
`POST /control {"fail_next": 2}` makes the next two deliveries fail with 500 so retries are visible.
"""
from __future__ import annotations

import json
import os
import threading
import time

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from docverify.callbacks import verify

API = os.environ.get("DOCVERIFY_API", "http://127.0.0.1:8501")
SELF = os.environ.get("MOCK_PLATFORM_URL", "http://127.0.0.1:8511")
PLATFORMS = ("ecommerce", "ads", "live", "payments", "learn")

app = FastAPI(title="mock platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
secrets: dict[str, str] = {}
received: list[dict] = []
seen: set[str] = set()
state = {"fail_next": 0, "registered": False, "error": ""}
lock = threading.Lock()


def register() -> None:
    for _ in range(120):
        try:
            with httpx.Client(base_url=API, timeout=5) as c:
                for p in PLATFORMS:
                    tok = c.post("/v1/auth/token", json={"client_id": f"{p}-demo",
                                                         "client_secret": f"demo-secret-{p}"}).json()["access_token"]
                    r = c.put("/v1/webhooks", json={"url": f"{SELF}/hooks/{p}"},
                              headers={"Authorization": f"Bearer {tok}"})
                    r.raise_for_status()
                    secrets[p] = r.json()["secret"]
            state["registered"] = True
            return
        except Exception as e:  # API not up yet
            state["error"] = str(e)[:200]
            time.sleep(1)


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=register, daemon=True).start()


@app.post("/hooks/{platform}")
async def hook(platform: str, request: Request):
    body = await request.body()
    sig = request.headers.get("X-DocVerify-Signature", "")
    event_id = request.headers.get("X-DocVerify-Event-Id", "")
    with lock:
        if state["fail_next"] > 0:
            state["fail_next"] -= 1
            received.append({"platform": platform, "event_id": event_id, "result": "simulated-500",
                             "at": time.time(), "signature": sig, "payload": json.loads(body)})
            return Response(status_code=500, content="simulated outage")
        valid = platform in secrets and verify(secrets[platform], body, sig)
        duplicate = event_id in seen
        if valid:
            seen.add(event_id)
        received.append({"platform": platform, "event_id": event_id, "at": time.time(), "signature": sig,
                         "result": "duplicate" if duplicate else ("ok" if valid else "bad-signature"),
                         "payload": json.loads(body)})
    return Response(status_code=200 if valid else 401)


@app.get("/received")
def get_received(case_id: str | None = None):
    items = [r for r in received if case_id is None or r["payload"].get("case_id") == case_id]
    return {"registered": state["registered"], "error": state["error"], "items": items[::-1][:200]}


@app.post("/control")
def control(body: dict):
    state["fail_next"] = int(body.get("fail_next", 0))
    return state
