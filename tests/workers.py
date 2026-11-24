import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def start_worker(worker_id: str, env: dict | None = None) -> subprocess.Popen:
    e = {**os.environ, **(env or {}), "PYTHONUNBUFFERED": "1"}
    log = open(ROOT / ".runtime" / f"{worker_id}.log", "w")
    return subprocess.Popen([sys.executable, "-m", "docverify.worker", "--id", worker_id], cwd=ROOT, env=e,
                            stdout=log, stderr=subprocess.STDOUT)


def stop(procs):
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
