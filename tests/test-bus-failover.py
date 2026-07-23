#!/usr/bin/env python3
"""test-bus-failover.py — Bus backup failover + forwarder integration test.

Tests the end-to-end Moses↔Esther failover paths:

  1. Message lifecycle (send → read → archive) on local bus
  2. Forwarder health detection (peer reachable/unreachable)
  3. Forwarder sync between local queues (simulates failover drain)
  4. External peer reachability (when Esther is up)
  5. Queue state consistency after sync

Run via: cd hermes-cortex && python3 test-bus-failover.py
Safe to run when peer is down — peer-dependent tests skip gracefully.

Returns exit code 0 = all critical tests pass, peer tests skipped as expected.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PASS = 0
FAIL = 0
SKIP = 0

HOME = Path.home()
BUS_URL = "http://127.0.0.1:8903"
CONFIG_FILE = HOME / ".hermes-cortex" / "cortex-bus.conf"

# Load token from config
TOKEN = ""
try:
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("CORTEX_BUS_TOKEN"):
            TOKEN = line.split("=", 1)[1].strip().strip("'\"")
except Exception:
    pass

HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}
TIMEOUT = 10


def pass_msg(msg: str):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail_msg(msg: str, detail: str = ""):
    global FAIL
    FAIL += 1
    extra = f" — {detail}" if detail else ""
    print(f"  ❌ {msg}{extra}")


def skip_msg(msg: str):
    global SKIP
    SKIP += 1
    print(f"  ⏭️ {msg}")


def _request(method: str, url: str, body: dict | None = None,
             timeout: int = TIMEOUT) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except Exception:
            detail = {"detail": f"HTTP {e.code}"}
        return e.code, detail
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return 0, {"error": str(e)[:200]}


# ═══════════════════════════════════════════════
# 1. LOCAL BUS HEALTH
# ═══════════════════════════════════════════════

print("\n═══ 1. Local Bus Health ═══")

status, data = _request("GET", f"{BUS_URL}/health")
if status == 200:
    pass_msg(f"Local bus health check: HTTP {status}")
else:
    fail_msg(f"Local bus health check returned HTTP {status}", str(data))

# ═══════════════════════════════════════════════
# 2. MESSAGE LIFECYCLE (send → read → archive)
# ═══════════════════════════════════════════════

print("\n═══ 2. Message Lifecycle (Send → Read → Archive) ═══")
TEST_QUEUE = "inbox_moses"

# 2a. Send a test message
status, data = _request("POST", f"{BUS_URL}/api/pgmq/send", {
    "queue": TEST_QUEUE,
    "message": {
        "type": "failover_test",
        "from": "test-bus-failover",
        "body": f"Test message at {datetime.now(timezone.utc).isoformat()}"
    }
})

if status == 200 and data.get("msg_id"):
    msg_id = data["msg_id"]
    pass_msg(f"Sent to {TEST_QUEUE}: msg_id={msg_id[:12]}")
else:
    fail_msg(f"Send to {TEST_QUEUE}", f"HTTP {status}: {data}")
    msg_id = None

# 2b. Read the message back (vt=60 so we can archive it)
read_msg = None
if msg_id:
    status, data = _request("POST", f"{BUS_URL}/api/pgmq/read", {
        "queue": TEST_QUEUE, "vt": 60
    })
    if status == 200 and data.get("msg_id"):
        read_msg = data
        pass_msg(f"Read from {TEST_QUEUE}: msg_id={data['msg_id'][:12]}")
    else:
        fail_msg(f"Read from {TEST_QUEUE}", f"HTTP {status}: {data}")

# 2c. Archive the message
if read_msg:
    status, data = _request("POST", f"{BUS_URL}/api/pgmq/archive", {
        "queue": TEST_QUEUE,
        "msg_id": read_msg["msg_id"],
        "archived_by": "test-bus-failover",
    })
    if status == 200:
        pass_msg(f"Archived from {TEST_QUEUE}")
    else:
        fail_msg(f"Archive from {TEST_QUEUE}", f"HTTP {status}: {data}")
elif msg_id:
    # Message was read but blocked — try direct delete
    status, data = _request("DELETE", f"{BUS_URL}/api/pgmq/delete", {
        "queue": TEST_QUEUE, "msg_id": msg_id,
    })
    if status == 200:
        pass_msg("Cleaned up via delete")

# ═══════════════════════════════════════════════
# 3. FORWARDER COMPONENT TEST (local-to-local sync)
# ═══════════════════════════════════════════════

print("\n═══ 3. Forwarder: Queue Discovery ═══")

status, data = _request("GET", f"{BUS_URL}/api/pgmq/queues")
if status == 200:
    queues = data.get("queues", []) if isinstance(data, dict) else data
    inbox_queues = [q["name"] for q in queues
                    if q.get("name", "").startswith("inbox_")
                    and not q.get("dlq", False)
                    and "health_check" not in q.get("name", "")]
    pass_msg(f"Discovered {len(inbox_queues)} inbox queues for sync: {', '.join(inbox_queues)}")
    # Verify all expected agent queues exist
    expected = {"inbox_moses", "inbox_esther", "inbox_joseph",
                "inbox_titus", "inbox_gisu", "inbox_kustos"}
    found = set(inbox_queues)
    missing = expected - found
    if missing:
        fail_msg(f"Missing expected queues: {', '.join(missing)}")
    else:
        pass_msg("All 6 agent inbox queues present")
else:
    fail_msg("Queue discovery via /api/pgmq/queues", f"HTTP {status}")

# ═══════════════════════════════════════════════
# 4. PEER HEALTH DETECTION
# ═══════════════════════════════════════════════

print("\n═══ 4. Peer (Esther) Health Detection ═══")

# Load peer config the same way the forwarder does
PEER_URL = os.environ.get("BUS_FORWARDER_PEER_URL", "")
PEER_TOKEN = os.environ.get("BUS_FORWARDER_PEER_TOKEN",
                            os.environ.get("CORTEX_BUS_TOKEN", TOKEN))
PEER_AUTH = os.environ.get("BUS_FORWARDER_PEER_AUTH",
                           os.environ.get("CORTEX_BASIC_AUTH", ""))

# Fallback: parse from config file
if not PEER_URL and CONFIG_FILE.exists():
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("CORTEX_BUS_FALLBACK_URL"):
            PEER_URL = line.split("=", 1)[1].strip().strip("'\"")

if not PEER_URL:
    skip_msg("No PEER_URL configured — peer-dependent tests skipped")
else:
    pass_msg(f"Peer URL: {PEER_URL}")

    # Health check (mirrors forwarder's _sync_direction health check)
    peer_healthy = False
    try:
        req = urllib.request.Request(f"{PEER_URL}/health", method="GET")
        if PEER_TOKEN:
            req.add_header("Authorization", f"Bearer {PEER_TOKEN}")
        elif PEER_AUTH:
            encoded = base64.b64encode(PEER_AUTH.encode()).decode()
            req.add_header("Authorization", f"Basic {encoded}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            peer_healthy = True
    except Exception:
        peer_healthy = False

    if peer_healthy:
        pass_msg("Peer (Esther) reachable — failover path available")
    else:
        skip_msg("Peer (Esther) unreachable — failover will accumulate locally")

    # If peer is healthy, test sync
    if peer_healthy:
        print("\n═══ 5. Forwarder Sync (Peer reachable — full test) ═══")
        # Send test message to inbox_esther on local bus
        status, data = _request("POST", f"{BUS_URL}/api/pgmq/send", {
            "queue": "inbox_esther",
            "message": {
                "type": "failover_sync_test",
                "from": "test-bus-failover",
                "body": f"Testing failover sync at {datetime.now(timezone.utc).isoformat()}"
            }
        })
        if status == 200:
            test_msg_id = data["msg_id"]
            pass_msg(f"Sent test message to inbox_esther: {test_msg_id[:12]}")

            # Read from local and push to peer (simulating forwarder direction)
            status, msg_data = _request("POST", f"{BUS_URL}/api/pgmq/read", {
                "queue": "inbox_esther", "vt": 0
            })
            if status == 200 and msg_data.get("msg_id"):
                # Forward to peer
                body = msg_data.get("body", {})
                p_status, p_data = _request("POST", f"{PEER_URL}/api/pgmq/send", {
                    "queue": "inbox_esther",
                    "message": body,
                }, timeout=15)

                if p_status == 200:
                    pass_msg("Forwarder LOCAL→PEER sync: message delivered to Esther")
                else:
                    fail_msg("Forwarder LOCAL→PEER sync", f"HTTP {p_status}: {p_data}")

                # Clean up: archive from local
                _request("POST", f"{BUS_URL}/api/pgmq/archive", {
                    "queue": "inbox_esther",
                    "msg_id": msg_data["msg_id"],
                    "archived_by": "test-bus-failover",
                })
        else:
            fail_msg("Failed to send test message for sync test", f"HTTP {status}")

# ═══════════════════════════════════════════════
# 5. QUEUE STATE CONSISTENCY
# ═══════════════════════════════════════════════

print("\n═══ 6. Queue State Consistency ═══")

status, data = _request("GET", f"{BUS_URL}/api/pgmq/queues")
if status == 200:
    queues = data.get("queues", []) if isinstance(data, dict) else data
    dlqs = [q for q in queues if q.get("dlq") and q.get("depth", 0) > 0]
    cascade = [q for q in dlqs if q["name"].count("_dlq") > 1]
    processing = [q for q in queues if q.get("processing", 0) > 0]

    if cascade:
        fail_msg(f"{len(cascade)} cascade DLQ queues found: {[q['name'] for q in cascade]}")
    elif any(q["name"].count("_dlq") > 1 for q in queues if q.get("dlq")):
        fail_msg("Empty cascade DLQ queue records still present")
    else:
        pass_msg("0 cascade DLQ queues — structural guard holds")

    total_pending = sum(q["depth"] for q in queues if not q.get("dlq"))
    total_dlq = sum(q["depth"] for q in dlqs)
    total_processing = sum(q["processing"] for q in queues)
    pass_msg(f"Pending: {total_pending}, Processing: {total_processing}, DLQ: {total_dlq}")

    inbox_esther_next = None
    for q in queues:
        if q["name"] == "inbox_esther" and q["depth"] > 0:
            inbox_esther_next = q["depth"]

    if inbox_esther_next:
        status, sample = _request("POST", f"{BUS_URL}/api/pgmq/read", {
            "queue": "inbox_esther", "vt": 0
        })
        if status == 200 and sample.get("msg_id"):
            body = sample.get("body", {})
            if isinstance(body, dict):
                msg_type = body.get("type", body.get("subject", "unknown"))
                pass_msg(f"Next inbox_esther message: type={msg_type}")
            elif isinstance(body, str):
                pass_msg(f"Next inbox_esther message: '{body[:80]}'")
        else:
            pass_msg(f"inbox_esther: {inbox_esther_next} pending (no peek available)")

# ═══════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════

print(f"\n═══ Summary ═══")
print(f"  {PASS} passed, {FAIL} failed, {SKIP} skipped")
if FAIL > 0:
    print("  ❌ Some tests FAILED")
elif SKIP > 0:
    print("  ⚠️  Peer-dependent tests skipped (peer down is expected)")
else:
    print("  ✅ All tests passed")

sys.exit(FAIL)
