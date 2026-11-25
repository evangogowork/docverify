#!/usr/bin/env bash
# One command: AWS (LocalStack), MySQL, Redis, API, 2 workers, callback dispatcher, mock platform, frontend.
# Ctrl-C stops the processes; `docker-compose -p docverify down` stops the containers.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE=${COMPOSE:-docker-compose}
mkdir -p .runtime
[ -d .venv ] || { python3.11 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
[ -d frontend/node_modules ] || (cd frontend && npm install --no-audit --no-fund)
./scripts/fetch_tessdata.sh >/dev/null
$COMPOSE up -d --wait
# Export before bootstrap: it seeds the demo clients/reviewers only when DOCVERIFY_SEED_DEMO=1.
export DOCVERIFY_SEED_DEMO=1 DOCVERIFY_LEARN_MODE=1
.venv/bin/python -m docverify.bootstrap
pids=()
.venv/bin/uvicorn docverify.api.main:app --port 8501 > .runtime/api.log 2>&1 & pids+=($!)
.venv/bin/python -m docverify.worker --id worker-1 > .runtime/worker-1.log 2>&1 & pids+=($!)
.venv/bin/python -m docverify.worker --id worker-2 > .runtime/worker-2.log 2>&1 & pids+=($!)
.venv/bin/python -m docverify.callbacks > .runtime/callbacks.log 2>&1 & pids+=($!)
.venv/bin/uvicorn mockplatform.app:app --port 8511 > .runtime/mockplatform.log 2>&1 & pids+=($!)
(cd frontend && npx vite --port 5501 --strictPort --host 127.0.0.1 > ../.runtime/frontend.log 2>&1) & pids+=($!)
trap 'kill ${pids[*]} 2>/dev/null; wait 2>/dev/null' INT TERM EXIT
for _ in $(seq 60); do curl -fs localhost:8501/v1/health >/dev/null && curl -fs localhost:5501 >/dev/null && break; sleep 1; done
echo
echo "  frontend      http://127.0.0.1:5501        (learn mode: /learn, interview: /learn/interview)"
echo "  API           http://127.0.0.1:8501/docs"
echo "  mock platform http://127.0.0.1:8511/received"
echo "  logs          .runtime/*.log"
echo
wait
