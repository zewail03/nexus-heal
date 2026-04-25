"""
Seed the dashboard with a handful of pre-baked alerts so it isn't
empty when the professor first opens it.

Usage
-----
    # In one terminal:
    python main.py

    # In another:
    python -m demo.preload

The seeded alerts cover four distinct runbook categories so the
demo can show retrieval breadth + the prompt-leak fix narrative
without needing to type anything live.
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx


SEEDS = [
    # Original 4 — covers M2 alert types
    ("DEMO-CPU-001",      "CPU usage 98.7% on api-gateway-prod, OOM killer active, connection pool exhausted"),
    ("DEMO-DB-001",       "Database connection pool exhausted on primary PostgreSQL, 503 errors on /api/users"),
    ("DEMO-DISK-001",     "Disk usage 97% on /var/log volume, 'No space left on device' errors in app logs"),
    ("DEMO-SSL-001",      "SSL certificate expired on api.example.com, HTTPS handshake failures across all clients"),
    # 4 from the expanded 16-runbook M3-stretch set — shows KB breadth
    ("DEMO-DNS-001",      "Coredns pods returning SERVFAIL, DNS lookup latency p99 above 500ms cluster-wide"),
    ("DEMO-KAFKA-001",    "Kafka consumer-group lag 250k records on payments topic, partition 7 hot, workers CPU-bound"),
    ("DEMO-DEADLOCK-001", "Postgres deadlocks spiking on accounts table, two transactions taking row-locks in opposite order"),
    ("DEMO-CDN-001",      "CloudFront cache-hit ratio dropped from 92% to 48% after deploy, origin egress 6x normal"),
]

DEFAULT_API = "http://127.0.0.1:8000"


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the NEXUS-HEAL dashboard with demo alerts.")
    parser.add_argument("--api", default=DEFAULT_API, help=f"FastAPI base URL (default {DEFAULT_API})")
    parser.add_argument("--approve", action="store_true",
                        help="Also POST /approve for each alert so the Watcher runs and the cards show 'executed'.")
    args = parser.parse_args()

    print(f"[demo] target API: {args.api}")
    print(f"[demo] {len(SEEDS)} seed alerts queued")

    # Health check first so we fail fast with a useful message
    try:
        r = httpx.get(f"{args.api}/health", timeout=5)
        r.raise_for_status()
    except Exception as e:
        print(f"[demo] FastAPI health check failed: {e}")
        print(f"[demo] Is `python main.py` running on {args.api}?")
        return 1

    posted = 0
    approved = 0
    t0 = time.perf_counter()

    for alert_id, alert_text in SEEDS:
        print(f"[demo] -> {alert_id}: {alert_text[:60]}...")
        try:
            r = httpx.post(
                f"{args.api}/analyze",
                json={"alert_id": alert_id, "alert_text": alert_text, "source": "demo-preload"},
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            sev = data.get("severity", "?")
            conf = float(data.get("confidence", 0.0)) * 100
            print(f"[demo]    classified as {data.get('alert_type','?')} ({sev}, conf {conf:.0f}%)")
            posted += 1
        except Exception as e:
            print(f"[demo]    FAILED: {type(e).__name__}: {e}")
            continue

        if args.approve:
            try:
                ar = httpx.post(
                    f"{args.api}/approve/{alert_id}",
                    params={"approved": "true"},
                    timeout=30,
                )
                ar.raise_for_status()
                outcome = ar.json()
                cmd_count = len(outcome.get("command_results", []))
                exe_count = sum(1 for r in outcome.get("command_results", []) if r.get("executed"))
                print(f"[demo]    approved -> status={outcome.get('execution_status','?')}  "
                      f"({exe_count}/{cmd_count} safe commands ran)")
                approved += 1
            except Exception as e:
                print(f"[demo]    approve failed: {type(e).__name__}: {e}")

    elapsed = time.perf_counter() - t0
    print(f"[demo] done — {posted}/{len(SEEDS)} analyzed, "
          f"{approved} approved, in {elapsed:.1f}s")
    return 0 if posted == len(SEEDS) else 1


if __name__ == "__main__":
    sys.exit(main())
