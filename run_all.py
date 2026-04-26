"""
NEXUS-HEAL — one-shot runner.

Runs every phase of the system end-to-end:

    1.  Pre-flight  : Python version, .env, dependencies, runbook count
    2.  Unit tests  : tests/test_watcher.py + tests/test_storage.py (no Groq)
    3.  Retrieval   : eval/retrieval_metrics.py against the 26-runbook KB
    4.  E2E tests   : tests/test_e2e.py (needs GROQ_API_KEY)
    5.  Reliability : eval/reliability_context.py + groundedness (--full only)
    6.  Live        : starts FastAPI + Streamlit, seeds 8 demo alerts
                      (Ctrl-C to stop)

Usage
-----
    python run_all.py                # quick: phases 1-4 + 6
    python run_all.py --full         # also run reliability checks (~10 min)
    python run_all.py --no-services  # skip phase 6 (no live demo)
    python run_all.py --check        # phase 1 only, no execution
    python run_all.py --quick        # alias for default

Each phase reports [PASS] / [FAIL] / [SKIP]. The script returns non-zero
if any required phase fails. Background services are killed on exit.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

# Background process handles for cleanup
_PROCS: list[subprocess.Popen] = []


# ---------------------------------------------------------------------------
# Pretty-print helpers (ASCII-only — Windows terminals trip on emoji)
# ---------------------------------------------------------------------------

def _colour(code: str, msg: str) -> str:
    if not sys.stdout.isatty():
        return msg
    return f"\033[{code}m{msg}\033[0m"


def header(label: str) -> None:
    bar = "=" * 70
    print()
    print(_colour("1;36", bar))
    print(_colour("1;36", f"  {label}"))
    print(_colour("1;36", bar))


def step(msg: str) -> None:
    print(_colour("0;36", f"  > {msg}"))


def ok(msg: str) -> None:
    print(_colour("1;32", f"  [PASS] {msg}"))


def fail(msg: str) -> None:
    print(_colour("1;31", f"  [FAIL] {msg}"))


def skip(msg: str) -> None:
    print(_colour("1;33", f"  [SKIP] {msg}"))


def info(msg: str) -> None:
    print(_colour("0;37", f"         {msg}"))


# ---------------------------------------------------------------------------
# Phase 1 — pre-flight
# ---------------------------------------------------------------------------

def phase_preflight() -> bool:
    header("Phase 1 / Pre-flight checks")

    all_good = True

    # Python version
    py_ver = sys.version_info
    step(f"Python: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver < (3, 11):
        fail("Need Python >= 3.11 (project tested on 3.13)")
        all_good = False
    else:
        ok("Python version OK")

    # .env file
    env_path = ROOT / ".env"
    if env_path.exists():
        ok(".env present")
    else:
        fail(".env missing — copy .env.example and fill in GROQ_API_KEY + Telegram tokens")
        all_good = False

    # Required runtime deps
    required = ["langgraph", "langchain_groq", "chromadb", "fastapi", "uvicorn", "httpx", "pytest"]
    missing = [m for m in required if importlib.util.find_spec(m) is None]
    if missing:
        fail(f"Missing required packages: {', '.join(missing)}")
        info("Install with: pip install -r requirements.txt")
        all_good = False
    else:
        ok(f"All {len(required)} required packages installed")

    # Optional UI deps
    ui_optional = ["plotly", "streamlit", "streamlit_extras", "streamlit_lottie"]
    ui_missing = [m for m in ui_optional if importlib.util.find_spec(m) is None]
    if ui_missing:
        info(f"UI deps missing (won't break tests): {', '.join(ui_missing)}")
    else:
        ok("UI deps installed (Streamlit demo will work)")

    # Knowledge base
    kb_path = ROOT / "knowledge_base"
    if kb_path.exists():
        runbooks = list(kb_path.glob("runbook_*.md"))
        if len(runbooks) >= 10:
            ok(f"Knowledge base: {len(runbooks)} runbooks")
        else:
            fail(f"Knowledge base only has {len(runbooks)} runbooks (expected 10+)")
            all_good = False
    else:
        fail("knowledge_base/ directory missing")
        all_good = False

    # GROQ_API_KEY (warn, don't fail — needed for e2e + live demo)
    # Re-load .env so a freshly-edited file takes effect this session.
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        pass
    if os.getenv("GROQ_API_KEY"):
        ok("GROQ_API_KEY set (e2e tests + live demo will work)")
    else:
        info("GROQ_API_KEY not set — e2e tests + live demo will skip")

    return all_good


# ---------------------------------------------------------------------------
# Phase 2 — deterministic unit tests
# ---------------------------------------------------------------------------

def phase_unit_tests() -> bool:
    header("Phase 2 / Deterministic unit tests (no Groq, no ChromaDB)")
    step("Running tests/test_watcher.py + tests/test_storage.py")
    rc = subprocess.call(
        [PYTHON, "-m", "pytest", "tests/test_watcher.py", "tests/test_storage.py", "-q"],
        cwd=ROOT,
    )
    if rc == 0:
        ok("All deterministic tests passed")
        return True
    fail(f"pytest exited {rc}")
    return False


# ---------------------------------------------------------------------------
# Phase 3 — retrieval eval (offline)
# ---------------------------------------------------------------------------

def phase_retrieval_eval() -> bool:
    header("Phase 3 / Retrieval metrics (offline — ChromaDB only)")
    step("Running python -m eval.retrieval_metrics --name run_all")
    rc = subprocess.call(
        [PYTHON, "-m", "eval.retrieval_metrics", "--name", "run_all"],
        cwd=ROOT,
    )
    if rc == 0:
        ok("Retrieval metrics computed")
        info("Outputs: eval/results/run_all_metrics.csv + run_all_summary.json")
        return True
    fail(f"retrieval_metrics exited {rc}")
    return False


# ---------------------------------------------------------------------------
# Phase 4 — e2e tests (needs Groq)
# ---------------------------------------------------------------------------

def phase_e2e_tests() -> bool:
    header("Phase 4 / End-to-end pipeline tests (needs Groq)")
    if not os.getenv("GROQ_API_KEY"):
        skip("GROQ_API_KEY not set — skipping e2e tests")
        return True  # not a failure
    step("Running tests/test_e2e.py")
    rc = subprocess.call(
        [PYTHON, "-m", "pytest", "tests/test_e2e.py", "-v"],
        cwd=ROOT,
    )
    if rc == 0:
        ok("E2E tests passed")
        return True
    fail(f"e2e tests exited {rc} (commonly: Groq TPD exhausted)")
    info("Set LLM_MODEL=llama-3.1-8b-instant to use the alternative quota")
    return False  # treated as fatal — explicit Groq failure


# ---------------------------------------------------------------------------
# Phase 5 — reliability checks (slow, needs Groq, --full only)
# ---------------------------------------------------------------------------

def phase_reliability(full: bool) -> bool:
    header("Phase 5 / Reliability checks (LLM-as-judge, needs Groq)")
    if not full:
        skip("Skipped by default. Re-run with --full to include (~10 minutes).")
        return True
    if not os.getenv("GROQ_API_KEY"):
        skip("GROQ_API_KEY not set — skipping reliability checks")
        return True

    rc1 = subprocess.call(
        [PYTHON, "-m", "eval.reliability_context", "--suffix", "_run_all"],
        cwd=ROOT,
    )
    rc2 = subprocess.call(
        [PYTHON, "-m", "eval.reliability_groundedness", "--suffix", "_run_all"],
        cwd=ROOT,
    )
    if rc1 == 0 and rc2 == 0:
        ok("Reliability checks complete")
        return True
    fail(f"reliability checks: context={rc1} groundedness={rc2}")
    return False


# ---------------------------------------------------------------------------
# Phase 6 — live services + seed
# ---------------------------------------------------------------------------

def _spawn(cmd: list[str], log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd, cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT,
    )
    _PROCS.append(proc)
    return proc


def _wait_for(url: str, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def phase_live(no_services: bool) -> bool:
    header("Phase 6 / Live demo — FastAPI + Streamlit + seeded alerts")
    if no_services:
        skip("--no-services passed — not starting FastAPI / Streamlit")
        return True
    if not os.getenv("GROQ_API_KEY"):
        skip("GROQ_API_KEY not set — can't run the pipeline live")
        return True

    logs = ROOT / ".run_all_logs"

    # FastAPI
    step("Starting FastAPI (port 8000) ...")
    api_proc = _spawn(
        [PYTHON, "-m", "uvicorn", "api.server:app", "--host", "127.0.0.1", "--port", "8000"],
        logs / "api.log",
    )
    if not _wait_for("http://127.0.0.1:8000/health", timeout_s=20):
        fail("FastAPI did not become healthy in 20s")
        info(f"Tail of api log: {logs / 'api.log'}")
        return False
    ok(f"FastAPI healthy (pid {api_proc.pid})")

    # Pre-warm ChromaDB by calling setup once
    step("Warming the vectorstore (one-time ingest) ...")
    rc = subprocess.call(
        [PYTHON, "-c", "from rag.vectorstore import setup_vectorstore; setup_vectorstore()"],
        cwd=ROOT,
    )
    if rc != 0:
        fail("vectorstore setup failed")
        return False
    ok("Vectorstore ready")

    # Streamlit
    step("Starting Streamlit dashboard (port 8501) ...")
    ui_proc = _spawn(
        [PYTHON, "-m", "streamlit", "run", "ui/app.py",
         "--server.headless=true", "--server.port=8501",
         "--browser.gatherUsageStats=false"],
        logs / "streamlit.log",
    )
    if not _wait_for("http://127.0.0.1:8501/", timeout_s=20):
        fail("Streamlit did not become healthy in 20s")
        info(f"Tail of streamlit log: {logs / 'streamlit.log'}")
        return False
    ok(f"Streamlit dashboard ready (pid {ui_proc.pid})")

    # Seed
    step("Seeding 8 demo alerts via demo/preload.py --approve ...")
    rc = subprocess.call([PYTHON, "-m", "demo.preload", "--approve"], cwd=ROOT)
    if rc == 0:
        ok("Demo alerts seeded and approved")
    else:
        info("Some seed alerts failed (commonly Groq TPD on 70B). Dashboard still works.")

    print()
    print(_colour("1;32", "  =================================================="))
    print(_colour("1;32", "  Live demo ready"))
    print(_colour("1;32", "  =================================================="))
    print(_colour("1;37", "  Dashboard : http://localhost:8501"))
    print(_colour("1;37", "  API docs  : http://localhost:8000/docs"))
    print(_colour("1;37", "  /alerts   : http://localhost:8000/alerts"))
    print(_colour("0;37", f"  Logs      : {logs / 'api.log'}, {logs / 'streamlit.log'}"))
    print()
    print(_colour("0;33", "  Press Ctrl-C to stop both services and exit."))

    # Block until user kills it
    try:
        while True:
            time.sleep(1)
            if api_proc.poll() is not None:
                fail("FastAPI process exited unexpectedly")
                return False
            if ui_proc.poll() is not None:
                fail("Streamlit process exited unexpectedly")
                return False
    except KeyboardInterrupt:
        print()
        info("Ctrl-C received, shutting down ...")
    return True


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _cleanup(*_args) -> None:
    for p in _PROCS:
        if p.poll() is None:
            try:
                if os.name == "nt":
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    p.terminate()
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Run every phase of NEXUS-HEAL end-to-end")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true",
                      help="Default: pre-flight + unit + retrieval + e2e + live (no reliability)")
    mode.add_argument("--full", action="store_true",
                      help="Add reliability checks (~10 min on Groq)")
    mode.add_argument("--check", action="store_true",
                      help="Pre-flight only, no execution")
    parser.add_argument("--no-services", action="store_true",
                        help="Skip starting FastAPI + Streamlit (Phase 6)")
    parser.add_argument("--no-tests", action="store_true",
                        help="Skip test phases (2 + 4)")
    parser.add_argument("--no-eval", action="store_true",
                        help="Skip retrieval eval (Phase 3)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _cleanup_and_exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _cleanup_and_exit)

    print(_colour("1;35", r"""
   _   _ _____ __  ___   _ ____         _   _ _____    _    _
  | \ | | ____|\ \/ / | | / ___|       | | | | ____|  / \  | |
  |  \| |  _|   \  /| | | \___ \ _____ | |_| |  _|   / _ \ | |
  | |\  | |___  /  \| |_| |___) |_____||  _  | |___ / ___ \| |___
  |_| \_|_____|/_/\_\\___/|____/       |_| |_|_____/_/   \_\_____|
"""))
    print(_colour("0;37", "  Network Expert Unified System for Healing, Error-Analysis & Logging"))
    print()

    failures: list[str] = []

    # Phase 1 — always
    if not phase_preflight():
        fail("Pre-flight checks failed — aborting.")
        return 1

    if args.check:
        print()
        ok("Pre-flight only (--check) — done.")
        return 0

    # Phase 2 — unit tests
    if not args.no_tests:
        if not phase_unit_tests():
            failures.append("unit tests")

    # Phase 3 — retrieval eval
    if not args.no_eval:
        if not phase_retrieval_eval():
            failures.append("retrieval eval")

    # Phase 4 — e2e tests
    if not args.no_tests:
        if not phase_e2e_tests():
            failures.append("e2e tests")

    # Phase 5 — reliability (only with --full)
    if not phase_reliability(args.full):
        failures.append("reliability checks")

    # Phase 6 — live demo
    if not phase_live(args.no_services):
        failures.append("live services")

    print()
    header("Summary")
    if failures:
        for f in failures:
            fail(f)
        info(f"{len(failures)} phase(s) failed.")
        return 1
    ok("All phases completed successfully.")
    return 0


def _cleanup_and_exit(*_args) -> None:
    _cleanup()
    sys.exit(0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        _cleanup()
