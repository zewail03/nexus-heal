#!/usr/bin/env bash
#
# NEXUS-HEAL deployment launcher (Render / single-container hosts).
#
# Boots FastAPI on the loopback (port 8000) in the background, waits for
# /health to come up, then runs Streamlit on $PORT (Render injects this
# automatically — defaults to 8501 for local dev). Both processes share
# the container; SIGTERM from the platform takes both down.

set -euo pipefail

INTERNAL_API_PORT="${FASTAPI_PORT:-8000}"
EXTERNAL_UI_PORT="${PORT:-8501}"

cleanup() {
    if [[ -n "${API_PID:-}" ]] && kill -0 "$API_PID" 2>/dev/null; then
        echo "[start] stopping FastAPI (pid=$API_PID)"
        kill "$API_PID" 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

echo "[start] launching FastAPI on 127.0.0.1:${INTERNAL_API_PORT}"
python main.py &
API_PID=$!

echo "[start] waiting for FastAPI /health (timeout 60 s)"
for _ in $(seq 1 60); do
    if python -c "import sys, urllib.request; urllib.request.urlopen('http://127.0.0.1:${INTERNAL_API_PORT}/health', timeout=2)" 2>/dev/null; then
        echo "[start] FastAPI ready"
        break
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "[start] FastAPI exited before /health came up — see logs above"
        exit 1
    fi
    sleep 1
done

echo "[start] launching Streamlit on 0.0.0.0:${EXTERNAL_UI_PORT}"
exec streamlit run ui/app.py \
    --server.port="${EXTERNAL_UI_PORT}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
