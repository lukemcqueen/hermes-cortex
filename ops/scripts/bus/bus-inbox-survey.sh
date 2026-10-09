#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  bus-inbox-survey.sh — Reproducible Agent Bus state check
#
#  Answers, with defensible output, the questions the
#  cortex-bus-{workday,evening,overnight} crons ask:
#    - any pending messages?
#    - any urgent/critical items?   (per-message `priority`: int 0-100;
#                                    >=10 urgent, >=20 critical; numeric
#                                    strings and "urgent"/"critical" accepted;
#                                    an unrecognised priority is flagged, not
#                                    silently downgraded)
#    - any blocked workflows?       (workflow_step_result backlog)
#    - any DLQ items?               (pending or processing)
#
#  Live mode queries the bus API. Fixture mode (BUS_SURVEY_FIXTURE=<file>)
#  reads {"queues":[...],"messages":{queue:[{priority,subject}]}} so the
#  logic is hermetically testable — see tests/test_bus_inbox_survey.py.
#
#  Fail-closed: an unexpected API response shape exits 1 rather than
#  reporting RESULT: clean. A queue whose depth exceeds the number of
#  messages actually inspected is reported as TRUNCATED and marked
#  actionable, so a hidden critical item cannot be reported as clean.
#
#  Exit codes:
#    0  survey ran (see RESULT line for actionable / clean)
#    1  could not verify the bus (API/shape failure)
#
#  Prints one line per problem; RESULT: clean only when nothing is actionable.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

BUS_BASE="${CORTEX_BUS_LOCAL_URL:-http://127.0.0.1:8903}"
ENV_FILE="${HOME}/hermes-cortex/.env"
PEEK_LIMIT="${BUS_SURVEY_PEEK_LIMIT:-500}"

if [[ -z "${BUS_SURVEY_FIXTURE:-}" && -z "${CORTEX_BUS_TOKEN:-}" && -r "$ENV_FILE" ]]; then
    # read token without echoing it
    CORTEX_BUS_TOKEN="$(grep -m1 '^CORTEX_BUS_TOKEN=' "$ENV_FILE" | cut -d= -f2- | tr -d '"'"'"' ')"
fi
export CORTEX_BUS_TOKEN BUS_BASE PEEK_LIMIT

python3 - <<'PY'
import os, sys, json, urllib.request, datetime

base = os.environ["BUS_BASE"]
fixture = os.environ.get("BUS_SURVEY_FIXTURE", "")
peek_limit = int(os.environ.get("PEEK_LIMIT", "500"))


def fail(msg):
    print("FAIL: " + msg, file=sys.stderr)
    sys.exit(1)


def http(path):
    req = urllib.request.Request(
        base + path,
        headers={"Authorization": "Bearer " + os.environ.get("CORTEX_BUS_TOKEN", "")})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)


def require_list(obj, key, where):
    if not isinstance(obj, dict) or not isinstance(obj.get(key), list):
        fail("unexpected %s response shape (%s): missing list %r" % (where, type(obj).__name__, key))
    return obj[key]


if fixture:
    try:
        data = json.load(open(fixture))
    except Exception as e:
        fail("cannot read fixture %s (%s)" % (fixture, e))
    queues = require_list(data, "queues", "fixture")
    messages = data.get("messages", {})
    if not isinstance(messages, dict):
        fail("fixture 'messages' must be an object")
else:
    try:
        queues = require_list(http("/api/pgmq/queues"), "queues", "/api/pgmq/queues")
    except SystemExit:
        raise
    except Exception as e:
        fail("bus API unreachable at %s (%s)" % (base, e))
    messages = {}
    for q in queues:
        name = q.get("name")
        if q.get("dlq") or not (q.get("depth", 0) or q.get("processing", 0)):
            continue
        if not name:
            fail("queue entry missing 'name'")
        try:
            messages[name] = require_list(
                http("/api/pgmq/peek/%s?limit=%d" % (name, peek_limit)),
                "messages", "/api/pgmq/peek/%s" % name)
        except SystemExit:
            raise
        except Exception as e:
            fail("peek failed for queue %s (%s)" % (name, e))

# ── Detection ────────────────────────────────────────────────
PRIORITY_STR = {"normal": 0, "urgent": 10, "critical": 20}


def as_priority(p):
    """Return (value, known). Numeric strings and known words map; anything
    else is reported as unknown rather than silently treated as normal."""
    if isinstance(p, bool):
        return 0, True
    if isinstance(p, (int, float)):
        return int(p), True
    if isinstance(p, str):
        s = p.strip().lower()
        if s in PRIORITY_STR:
            return PRIORITY_STR[s], True
        try:
            return int(s), True
        except ValueError:
            return 0, False
    return 0, False


active = [q for q in queues if q.get("depth", 0) or q.get("processing", 0)]
dlq = [q for q in queues if q.get("dlq") and (q.get("depth", 0) or q.get("processing", 0))]
blocked = [q for q in queues if q["name"] == "workflow_step_result"
           and (q.get("depth", 0) or q.get("processing", 0))]

urgent = []
unknown = []
truncated = []
for q in active:
    if q.get("dlq"):
        continue
    name = q["name"]
    seen = messages.get(name, [])
    depth = q.get("depth", 0)
    if depth > len(seen):
        truncated.append((name, depth, len(seen)))
    for m in seen:
        value, known = as_priority(m.get("priority", 0))
        if not known:
            unknown.append((name, m.get("priority")))
        elif value >= 20:
            urgent.append((name, "critical", m.get("subject", "?")))
        elif value >= 10:
            urgent.append((name, "urgent", m.get("subject", "?")))

for q in active:
    print("pending: %s depth=%s processing=%s" % (q["name"], q["depth"], q["processing"]))
for q in dlq:
    print("DLQ:     %s depth=%s processing=%s" % (q["name"], q["depth"], q["processing"]))
for q in blocked:
    print("BLOCKED: workflow_step_result depth=%s processing=%s" % (q["depth"], q["processing"]))
for qname, level, subject in urgent:
    print("%s: %s subject=%s" % (level.upper(), qname, subject))
for name, depth, seen in truncated:
    print("TRUNCATED: %s depth=%s inspected=%s — unreviewed messages remain" % (name, depth, seen))
for name, raw in unknown:
    print("WARN: %s has unrecognised priority %r — treated as actionable" % (name, raw))

actionable = bool(dlq or blocked or urgent or truncated or unknown)
now = datetime.datetime.now(datetime.timezone.utc)
print("RESULT: %s (active_queues=%d dlq=%d blocked=%d urgent=%d truncated=%d unknown=%d checked_at=%s)" % (
    "actionable" if actionable else "clean",
    len(active), len(dlq), len(blocked), len(urgent), len(truncated), len(unknown),
    now.isoformat(timespec="seconds")))
PY
