#!/usr/bin/env python3
"""
Agent Bus Integration Test Suite — Run after building or modifying the bus.

Tests all endpoints, auth, permissions, error handling, and edge cases.
Returns non-zero exit code if any test fails.

Usage:
    CORTEX_BUS_PG_HOST=127.0.0.1 CORTEX_BUS_PG_PORT=15432 \
    CORTEX_BUS_PG_USER=gbrain CORTEX_BUS_PG_PASS=... \
    python3 test_orch_bus.py
"""

import json
import os
import sys
import uuid
import urllib.request
import urllib.error

BASE_URL = os.environ.get("CORTEX_BUS_TEST_URL", "http://127.0.0.1:8906")
TOKENS = {
    "moses": os.environ.get("CORTEX_BUS_TOKEN_MOSES", "hbus_841a44b5c05ccbf7ec65fd1ff52d24085dbfa36b28122cb56cca0fd9fe20a479"),
    "esther": os.environ.get("CORTEX_BUS_TOKEN_ESTHER", "hbus_cd477348ba6fdff697bb37b178529712f60ac55c9fb30a60b082d8888b76a076"),
    "joseph": os.environ.get("CORTEX_BUS_TOKEN_JOSEPH", "hbus_cec6d9da7c01746f230647c670fdd5b20a35842c9ff6de58b76f38bdb59d5e7e"),
}

PASS = 0
FAIL = 0
ERRORS = []


def request(method, path, token=None, body=None):
    """Make an HTTP request to the bus server."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {"detail": e.reason if hasattr(e, 'reason') else f"HTTP {e.code}"}
        return e.code, body
    except urllib.error.URLError as e:
        return 0, {"error": str(e.reason)}


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        msg = f"  ❌ {name} — {detail}" if detail else f"  ❌ {name}"
        print(msg)
        ERRORS.append(f"{name}: {detail}")


def section(name):
    print(f"\n━━━ {name} ━━━")


# ── Tests ────────────────────────────────────────────────────

def drain_queue(queue, token, max_drain=10):
    """Drain all messages from a queue (for cleanup)."""
    for _ in range(max_drain):
        _, data = request("POST", "/api/pgmq/read", token=token, body={"queue": queue, "vt": 5})
        if data.get("msg_id"):
            request("POST", "/api/pgmq/archive", token=token, body={"queue": queue, "msg_id": data["msg_id"]})
        else:
            break

section("Cleanup — Drain leftover messages")
drain_queue("inbox_moses", TOKENS["moses"])
drain_queue("inbox_test_dlq", TOKENS["moses"])
drain_queue("inbox_test_dlq_dlq", TOKENS["moses"])

section("Health Check")
status, data = request("GET", "/health")
test("Health returns 200", status == 200)
test("Backend is pgmq", data.get("backend") == "pgmq")
test("Queues count > 0", data.get("queues", 0) > 0)

section("Auth — No Token / Bad Token")
status, data = request("GET", "/api/pgmq/queues")
test("No token → 401", status == 401, data.get("detail", ""))

status, data = request("GET", "/api/pgmq/queues", token="badtoken")
test("Bad token → 401", status == 401, data.get("detail", ""))

status, data = request("GET", "/api/pgmq/queues", token=TOKENS["moses"])
test("Valid token → 200", status == 200, data.get("detail", ""))

section("Send — Basic")
status, data = request("POST", "/api/pgmq/send", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "message": {"from": "moses", "subject": "basic", "body": "hello"},
})
test("Send returns msg_id", "msg_id" in data, str(data.get("msg_id", ""))[:16])
MOSES_MSG = data.get("msg_id", "")

section("Send — With Priority and Correlation")
status, data = request("POST", "/api/pgmq/send", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "message": {"from": "moses", "subject": "high priority", "body": "urgent"},
    "priority": 10,
    "correlation_id": "corr-001",
})
test("High priority send", "msg_id" in data)

section("Send — Error Cases")
status, data = request("POST", "/api/pgmq/send", token=TOKENS["moses"], body={})
test("Send without queue rejected", status in (400, 422), f"status={status} detail={data.get('detail','')[:50]}")

section("Read — Basic")
status, data = request("POST", "/api/pgmq/read", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "vt": 30,
})
test("Read returns msg", "msg_id" in data and data["msg_id"], str(data.get("msg_id", ""))[:16])
READ_MSG = data.get("msg_id", "")

section("Read — Priority Ordering")
# The high-priority message (priority=10) should come before the basic one (priority=0)
test("High priority read first", data.get("priority") == 10, f"got priority={data.get('priority')}")

section("Archive — Basic")
status, data = request("POST", "/api/pgmq/archive", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "msg_id": READ_MSG,
})
test("Archive returns success", data.get("success") is True)

section("Archive — Invalid UUID")
status, data = request("POST", "/api/pgmq/archive", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "msg_id": "not-a-uuid",
})
test("Archive bad UUID → 400", status == 400)

section("Read — Empty Queue")
# Drain remaining messages from prior tests
_, drain_data = request("POST", "/api/pgmq/read", token=TOKENS["moses"], body={"queue": "inbox_moses", "vt": 5})
if drain_data.get("msg_id"):
    request("POST", "/api/pgmq/archive", token=TOKENS["moses"], body={"queue": "inbox_moses", "msg_id": drain_data["msg_id"]})

# Now queue should be truly empty
status, data = request("POST", "/api/pgmq/read", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "vt": 5,
})
test("Empty read returns msg_id = None", data.get("msg_id") is None, f"got msg_id={data.get('msg_id')}")

section("Requeue — Basic")
# First send a new message to requeue
status, data = request("POST", "/api/pgmq/send", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "message": {"test": "requeue demo"},
})
RQ_ID = data.get("msg_id", "")

# Read it
status, data = request("POST", "/api/pgmq/read", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "vt": 5,
})

# Requeue it
status, data = request("POST", "/api/pgmq/requeue", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "msg_id": data.get("msg_id"),
    "error": "test failure",
})
test("Requeue returns success", data.get("success") is True)

# Read it back — should be available again
status, data = request("POST", "/api/pgmq/read", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "vt": 5,
})
test("Requeued message re-readable", data.get("msg_id") is not None)
test("Retry count incremented", data.get("retry_count", 0) == 1, f"retry_count={data.get('retry_count')}")

# Archive it to clean up
status, _ = request("POST", "/api/pgmq/archive", token=TOKENS["moses"], body={
    "queue": "inbox_moses",
    "msg_id": data.get("msg_id"),
})

section("Queue Depth")
status, data = request("GET", "/api/pgmq/depth/inbox_moses", token=TOKENS["moses"])
test("Depth returns number", "depth" in data)
test("Depth is 0 after cleanup", data.get("depth") == 0, f"depth={data.get('depth')}")

section("Queue List")
status, data = request("GET", "/api/pgmq/queues", token=TOKENS["moses"])
test("Queues list", "queues" in data)
test("All agent queues present", data.get("total", 0) >= 12, f"total={data.get('total')}")

# Verify specific queues exist
queue_names = [q["name"] for q in data.get("queues", [])]
for agent in ["moses", "esther", "joseph", "titus", "gisu", "kustos"]:
    test(f"Queue inbox_{agent} exists", f"inbox_{agent}" in queue_names)
    test(f"DLQ inbox_{agent}_dlq exists", f"inbox_{agent}_dlq" in queue_names)

section("Queue Detail")
status, data = request("GET", "/api/pgmq/queue/inbox_moses", token=TOKENS["moses"])
test("Queue detail returns name", data.get("name") == "inbox_moses")

# Nonexistent queue: permission check returns 403 (queue not in allowed list)
status, data = request("GET", "/api/pgmq/queue/nonexistent", token=TOKENS["moses"])

test("Nonexistent queue blocked", status in (403, 404), f"status={status} detail={data.get('detail','')[:50]}")

section("Permissions — Esther")
# Esther can read her own queue
status, data = request("GET", "/api/pgmq/depth/inbox_esther", token=TOKENS["esther"])
test("Esther reads her own queue → 200", status == 200)

# Esther CANNOT read Moses' queue
status, data = request("GET", "/api/pgmq/depth/inbox_moses", token=TOKENS["esther"])
test("Esther cannot read Moses queue → 403", status == 403, data.get("detail", ""))

# Esther can send to Moses
status, data = request("POST", "/api/pgmq/send", token=TOKENS["esther"], body={
    "queue": "inbox_moses",
    "message": {"from": "esther", "body": "report to moses"},
})
test("Esther sends to Moses → 200", status == 200)

# Esther can archive her own queue
# First send to esther, then read, then archive
ESTHER_SELF = uuid.uuid4().hex[:8]
status, send_data = request("POST", "/api/pgmq/send", token=TOKENS["moses"], body={
    "queue": "inbox_esther",
    "message": {"from": "moses", "body": f"hello esther {ESTHER_SELF}"},
})
test("Moses sends to Esther", "msg_id" in send_data)

status, read_data = request("POST", "/api/pgmq/read", token=TOKENS["esther"], body={
    "queue": "inbox_esther",
    "vt": 30,
})
test("Esther reads her queue", read_data.get("msg_id") is not None, str(read_data.get("msg_id", ""))[:16])

# Archive with esther's token
status, archive_data = request("POST", "/api/pgmq/archive", token=TOKENS["esther"], body={
    "queue": "inbox_esther",
    "msg_id": read_data.get("msg_id"),
})
test("Esther archives her own msg", archive_data.get("success") is True, f"status={status}")

section("Permissions — Joseph")
# Joseph cannot read Esther's queue
status, data = request("GET", "/api/pgmq/depth/inbox_esther", token=TOKENS["joseph"])
test("Joseph cannot read Esther queue → 403", status == 403, data.get("detail", ""))

# Joseph can send to Moses
status, data = request("POST", "/api/pgmq/send", token=TOKENS["joseph"], body={
    "queue": "inbox_moses",
    "message": {"from": "joseph", "body": "report"},
})
test("Joseph sends to Moses", status == 200)

section("Dashboard")
status, data = request("GET", "/api/bus/dashboard", token=TOKENS["moses"])
test("Dashboard returns status", data.get("status") == "ok")
test("Dashboard shows backend", "backend" in data)
test("Dashboard shows queue count", "queues" in data)
test("Dashboard shows circuit breaker", "circuit_breaker" in data)

section("HTML Dashboard")
# HTML dashboard returns HTML, not JSON. Just check status code.
import urllib.request
html_req = urllib.request.Request(f"{BASE_URL}/", headers={"Authorization": f"Bearer {TOKENS['moses']}"})
try:
    with urllib.request.urlopen(html_req, timeout=10) as resp:
        test("HTML dashboard returns 200", resp.status == 200)
except Exception as e:
    test("HTML dashboard returns 200", False, str(e))

section("Agent Card")
status, data = request("GET", "/.well-known/agent-card.json")
test("Agent card public (no auth needed)", status == 200)
test("Agent card has name", data.get("name") == "hermes-cortex-bus")

section("DLQ Flow")
# Ensure test DLQ queue exists
from agent_bus.queue import get_queue
bus = get_queue()
bus.create_queues_for_agent("test_dlq")

# Send and requeue 4 times to trigger DLQ
SEND_DLQ_STATUS, SEND_DLQ_DATA = request("POST", "/api/pgmq/send", token=TOKENS["moses"], body={
    "queue": "inbox_test_dlq",
    "message": {"test": "DLQ flow"},
})
DLQ_ID = SEND_DLQ_DATA.get("msg_id", "")

if DLQ_ID:
    for i in range(4):
        # Read
        _, read_data = request("POST", "/api/pgmq/read", token=TOKENS["moses"], body={
            "queue": "inbox_test_dlq",
            "vt": 5,
        })
        if read_data.get("msg_id"):
            # Requeue
            request("POST", "/api/pgmq/requeue", token=TOKENS["moses"], body={
                "queue": "inbox_test_dlq",
                "msg_id": read_data["msg_id"],
                "error": f"attempt {i+1}",
            })
    
    # Check if in DLQ
    _, depth_data = request("GET", "/api/pgmq/depth/inbox_test_dlq_dlq", token=TOKENS["moses"])
    test("Message in DLQ after 3+ retries", depth_data.get("depth", 0) > 0, f"DLQ depth={depth_data.get('depth')}")
    
    # Clean up
    _, read_dlq = request("POST", "/api/pgmq/read", token=TOKENS["moses"], body={
        "queue": "inbox_test_dlq_dlq",
        "vt": 5,
    })
    if read_dlq.get("msg_id"):
        request("POST", "/api/pgmq/archive", token=TOKENS["moses"], body={
            "queue": "inbox_test_dlq_dlq",
            "msg_id": read_dlq["msg_id"],
        })

# ── Final ────────────────────────────────────────────────────

print(f"\n{'═' * 50}")
print(f"Results: {PASS} passed, {FAIL} failed")
if ERRORS:
    print(f"\nFailures:")
    for e in ERRORS:
        print(f"  • {e}")
print(f"{'═' * 50}")

sys.exit(0 if FAIL == 0 else 1)
