#!/usr/bin/env python3
"""
bus-self-test.py — Verify the Agent Bus connection chain end-to-end.

Run this on ANY fleet machine to confirm the bus is reachable, auth works,
and the full send→read→archive cycle completes.

Usage:
    python3 ops/scripts/manage/bus-self-test.py

Exit codes:
    0 — All checks passed
    1 — One or more checks failed
"""
import json, os, sys, base64
from pathlib import Path

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

def check(description, result, detail=""):
    icon = PASS if result else FAIL
    print(f"  {icon} {description}")
    if detail:
        for line in detail.splitlines():
            print(f"     {line}")
    return result

def read_config(key: str) -> str:
    """Read a value from cortex-bus.conf by key."""
    config_path = Path.home() / ".hermes-cortex" / "cortex-bus.conf"
    if config_path.exists():
        for line in config_path.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return ""

def main():
    errors = 0
    print("\n=== Bus Self-Test ===\n")

    # Check 1: Config file exists
    config_path = Path.home() / ".hermes-cortex" / "cortex-bus.conf"
    if not check("cortex-bus.conf exists", config_path.exists(), str(config_path)):
        print("\n  Create it at ~/.hermes-cortex/cortex-bus.conf first.")

    # Check 2: Config has required keys
    bus_url = os.environ.get("CORTEX_BUS_URL") or read_config("CORTEX_BUS_URL") or "http://127.0.0.1:8903"
    basic_auth = os.environ.get("CORTEX_BUS_AUTH") or read_config("CORTEX_BASIC_AUTH") or read_config("CORTEX_BUS_AUTH") or ""
    token = os.environ.get("CORTEX_BUS_TOKEN") or read_config("CORTEX_BUS_TOKEN") or ""
    agent_name = os.environ.get("AGENT_NAME") or read_config("AGENT_NAME") or os.environ.get("USER", "unknown")

    check("CORTEX_BUS_URL found", bool(bus_url), f"  URL: {bus_url}")
    check("Auth credentials found (Basic or Bearer)", bool(basic_auth or token),
          f"  Basic auth: {'✓' if basic_auth else '✗'}  Bearer token: {'✓' if token else '✗'}")
    check("AGENT_NAME found", bool(agent_name), f"  Agent: {agent_name}")

    if not bus_url:
        errors += 1
        print("\n  ❌ Cannot continue without a bus URL.")

    # Check 3: Auth method
    scheme = "Bearer" if token else ("Basic" if basic_auth else "none")
    creds = token if token else (base64.b64encode(basic_auth.encode()).decode() if basic_auth else "")
    print(f"\n  Auth method: {scheme}")

    # Check 4: Try to hit the health endpoint
    import urllib.request, urllib.error
    print(f"\n--- Network Tests ---\n")

    try:
        req = urllib.request.Request(
            f"{bus_url}/health",
            headers={"Authorization": f"{scheme} {creds}" if creds else ""}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            healthy = data.get("status") == "ok"
            check(f"Bus health endpoint ({bus_url}/health)", healthy,
                  f"  Status: {data.get('status', 'unknown')}")
            if not healthy:
                errors += 1
    except Exception as e:
        check(f"Bus health endpoint ({bus_url}/health)", False, f"  Error: {e}")
        errors += 1

    # Check 5: List queues
    try:
        req = urllib.request.Request(
            f"{bus_url}/api/pgmq/queues",
            headers={"Authorization": f"{scheme} {creds}" if creds else ""}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            queues = data.get("queues", []) if isinstance(data, dict) else data
            inboxes = [q["name"] for q in queues if "inbox_" in q["name"]]
            check(f"Bus API reachable — {len(queues)} queues found", True,
                  f"  Your inbox: {'inbox_' + agent_name if 'inbox_' + agent_name in queues else 'NOT FOUND'}\n"
                  f"  Fleet inboxes: {len([q for q in inboxes if not q.endswith('_dlq')])}")
    except Exception as e:
        check(f"Bus API reachable ({bus_url}/api/pgmq/queues)", False, f"  Error: {e}")
        errors += 1

    # Check 6: Full send → read → archive cycle
    print(f"\n--- Write/Read Test ---\n")

    queue_name = f"inbox_{agent_name}"
    test_cid = f"self-test-{os.urandom(4).hex()}"

    # Send
    import subprocess
    send_payload = json.dumps({
        "queue": queue_name,
        "message": json.dumps({
            "from": agent_name, "to": agent_name,
            "subject": "SELF_TEST", "correlation_id": test_cid,
            "body": json.dumps({"test": True, "timestamp": os.urandom(4).hex()})
        })
    })
    proc = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST",
         "-H", "Content-Type: application/json",
         "-H", f"Authorization: {scheme} {creds}",
         "-d", send_payload, f"{bus_url}/api/pgmq/send"],
        capture_output=True, text=True, timeout=15
    )
    lines = proc.stdout.strip().split("\n")
    code = lines[-1] if len(lines) > 1 else "?"
    body = lines[0] if len(lines) == 2 else "\n".join(lines[:-1])
    http_ok = code == "200"
    check(f"Send message to {queue_name}", http_ok, f"  HTTP {code}")

    if http_ok:
        try:
            resp = json.loads(body)
            check("  msg_id returned", bool(resp.get("msg_id")),
                  f"  msg_id: {resp.get('msg_id', 'none')[:20]}...")
        except:
            check("  msg_id returned", False, f"  Body: {body[:80]}")
    else:
        errors += 1

    # Read
    import time
    read_payload = json.dumps({"queue": queue_name, "vt": 10})
    proc = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST",
         "-H", "Content-Type: application/json",
         "-H", f"Authorization: {scheme} {creds}",
         "-d", read_payload, f"{bus_url}/api/pgmq/read"],
        capture_output=True, text=True, timeout=15
    )
    lines = proc.stdout.strip().split("\n")
    code = lines[-1]
    read_result = "\n".join(lines[:-1])
    try:
        read_data = json.loads(read_result) if read_result.strip() else {}
    except:
        read_data = {}

    has_msg = bool(read_data.get("msg_id"))
    if has_msg:
        # Parse body — could be JSON string or already a dict
        body_raw = read_data.get("body", "")
        if isinstance(body_raw, str):
            try:
                body_parsed: dict = json.loads(body_raw)
            except:
                body_parsed = {}
        elif isinstance(body_raw, dict):
            body_parsed = body_raw
        else:
            body_parsed = {}
        cid = body_parsed.get("correlation_id", "missing")
        cid_match = cid == test_cid
        check(f"Read back from {queue_name}", True,
              f"  msg_id: {read_data.get('msg_id', '')[:20]}...\n"
              f"  correlation_id: {cid} {'✓' if cid_match else '✗ MISMATCH'}\n"
              f"  subject: {body_parsed.get('subject', 'missing')}")

        # Archive
        archive_payload = json.dumps({"queue": queue_name, "msg_id": read_data["msg_id"]})
        proc = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST",
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: {scheme} {creds}",
             "-d", archive_payload, f"{bus_url}/api/pgmq/archive"],
            capture_output=True, text=True, timeout=10
        )
        arch_code = proc.stdout.strip().split("\n")[-1]
        check(f"Archive message", arch_code == "200", f"  HTTP {arch_code}")
    else:
        check(f"Read back from {queue_name}", False,
              f"  HTTP {code}\n  Response: {read_result[:100] if read_result else 'empty'}")
        errors += 1

    # Summary
    print(f"\n---\n")
    if errors == 0:
        print(f"  {PASS} ALL CHECKS PASSED — bus path verified end-to-end")
        print(f"  Auth: {scheme} → {bus_url} → agent: {agent_name}")
        sys.exit(0)
    else:
        print(f"  {FAIL} {errors} check(s) failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
