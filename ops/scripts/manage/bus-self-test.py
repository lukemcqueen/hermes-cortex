#!/usr/bin/env python3
"""Bus Self-Test — verify the full bus round-trip on this agent.

Tests:
  1. cortex_bus module importable
  2. Bus health endpoint reachable
  3. Send a test message to own inbox
  4. Read it back
  5. Archive it

Outputs JSON for doctor integration. Exit code: 0 = all pass, 1 = any failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

CORTEX_DEPLOY_HOME = os.path.expanduser("~/.hermes-cortex")
SCRIPTS_DIR = os.path.join(CORTEX_DEPLOY_HOME, "scripts")
HOME = os.path.expanduser("~")

# Agent name — prefer env, then config file, then hostname fallback
AGENT_NAME = os.environ.get("AGENT_NAME", "")
if not AGENT_NAME:
    config_path = os.path.join(CORTEX_DEPLOY_HOME, "cortex-bus.conf")
    if os.path.exists(config_path):
        for line in open(config_path):
            if line.startswith("AGENT_NAME="):
                AGENT_NAME = line.split("=", 1)[1].strip()
                break
if not AGENT_NAME:
    import socket
    AGENT_NAME = socket.gethostname()


def log(msg: str):
    ts = time.strftime("%H:%M:%S", time.gmtime())
    print(f"[{ts}] [{AGENT_NAME}] {msg}", file=sys.stderr)


def _find_cortex_bus() -> str | None:
    """Find the directory containing the lib/ package with cortex_bus.py."""
    candidates = [
        SCRIPTS_DIR,                                          # ~/.hermes-cortex/scripts (contains lib/)
        os.path.join(CORTEX_DEPLOY_HOME, "scripts"),           # same expanded differently
        os.path.join(os.path.dirname(__file__), ".."),         # ops/scripts (from manage/)
    ]
    for path in candidates:
        resolved = os.path.realpath(path)
        if os.path.isfile(os.path.join(resolved, "lib", "cortex_bus.py")):
            return resolved
    return None


def import_cortex_bus():
    """Import and return cortex_bus module."""
    parent = _find_cortex_bus()
    if parent:
        sys.path.insert(0, parent)
    from lib import cortex_bus as _cb  # type: ignore
    return _cb


def test_import() -> dict:
    """Test 1: cortex_bus importable."""
    log("Test 1: cortex_bus import...")
    try:
        cb = import_cortex_bus()
        log(f"  cortex_bus imported: send={hasattr(cb, 'bus_send')}, read={hasattr(cb, 'bus_read')}")
        return {"test": "import", "status": "PASS", "detail": "cortex_bus importable"}
    except Exception as e:
        log(f"  FAIL: {e}")
        return {"test": "import", "status": "FAIL", "detail": f"cortex_bus import failed: {e}"}


def test_health() -> dict:
    """Test 2: Bus health endpoint."""
    log("Test 2: bus health endpoint...")
    try:
        cb = import_cortex_bus()
        bus_url = getattr(cb, 'config', {}).get("CORTEX_BUS_URL", "")
        if not bus_url:
            bus_url = os.environ.get("CORTEX_BUS_URL", "http://127.0.0.1:8903")

        import urllib.request
        req = urllib.request.Request(f"{bus_url}/health", method="GET")
        resp = urllib.request.urlopen(req, timeout=10)
        body = resp.read().decode()
        data = json.loads(body)
        ok = data.get("status") == "ok"
        log(f"  health: {data.get('status')} ({bus_url})")
        return {
            "test": "health",
            "status": "PASS" if ok else "FAIL",
            "detail": f"bus health: {data.get('status')} @ {bus_url}" if ok else f"unexpected response: {body[:100]}",
        }
    except Exception as e:
        log(f"  FAIL: {e}")
        return {"test": "health", "status": "FAIL", "detail": f"health check failed: {e}"}


def test_roundtrip() -> dict:
    """Test 3-5: Send → Read → Archive on own inbox."""
    log("Test 3-5: send → read → archive round-trip...")
    try:
        cb = import_cortex_bus()
        inbox = f"inbox_{AGENT_NAME}"
        corr_id = f"bus-self-test-{uuid.uuid4().hex[:12]}"

        # 3. Send
        log(f"  Sending to {inbox} (corr={corr_id[:16]}...)")
        send_result = cb.bus_send(inbox, {
            "from": AGENT_NAME,
            "to": AGENT_NAME,
            "topic": "self-test",
            "subject": "SELF_TEST",
            "correlation_id": corr_id,
            "body": {"test": True, "timestamp": time.time()},
        })
        if not send_result or not send_result.get("msg_id"):
            return {"test": "roundtrip", "status": "FAIL", "detail": "bus_send returned no msg_id"}
        sent_msg_id = send_result["msg_id"]
        log(f"  Sent: msg_id={sent_msg_id}")

        # 4. Read back
        log("  Reading back...")
        read_result = cb.bus_read(inbox, vt=10)
        if not read_result:
            return {"test": "roundtrip", "status": "FAIL", "detail": "bus_read returned nothing (message not found)"}
        read_corr = read_result.get("correlation_id", "")
        read_msg_id = read_result.get("msg_id", "")
        log(f"  Read: corr={read_corr[:16] if read_corr else '?'}... msg_id={read_msg_id}")

        if read_corr != corr_id:
            return {"test": "roundtrip", "status": "FAIL", "detail": f"correlation_id mismatch: sent={corr_id} read={read_corr}"}

        # 5. Archive
        log("  Archiving...")
        archive_result = cb.bus_archive(inbox, read_msg_id)
        log(f"  Archived: {archive_result}")
        return {
            "test": "roundtrip",
            "status": "PASS",
            "detail": f"send→read→archive OK (msg_id={sent_msg_id[:12]}...)",
        }

    except Exception as e:
        log(f"  FAIL: {e}")
        return {"test": "roundtrip", "status": "FAIL", "detail": f"round-trip exception: {e}"}


def main():
    log(f"Bus Self-Test starting (agent={AGENT_NAME})")
    results = []

    # Test 1: import
    results.append(test_import())

    # Test 2: health endpoint
    results.append(test_health())

    # Test 3-5: round-trip (only if import passed)
    if results[0]["status"] == "PASS":
        results.append(test_roundtrip())
    else:
        results.append({"test": "roundtrip", "status": "SKIP", "detail": "cortex_bus not importable — cannot test"})

    # Summary
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] == "SKIP")
    healthy = failed == 0

    summary = {
        "healthy": healthy,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "agent": AGENT_NAME,
        "results": results,
    }

    print(json.dumps(summary, indent=2))
    log(f"Result: {passed} pass, {failed} fail, {skipped} skip — {'HEALTHY' if healthy else 'ISSUES'}")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
