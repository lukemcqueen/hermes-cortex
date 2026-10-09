#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  bus-inbox-survey.sh — Reproducible Agent Bus state check
#
#  Answers, with defensible output, the questions the
#  cortex-bus-{workday,evening,overnight} crons ask:
#    - any pending messages?
#    - any urgent/critical items?   (per-message `priority`: int 0-100;
#                                    >=10 urgent, >=20 critical; the
#                                    strings "urgent"/"critical" also accepted)
#    - any blocked workflows?       (workflow_step_result backlog)
#    - any DLQ items?
#
#  Live mode queries the bus API. Fixture mode (BUS_SURVEY_FIXTURE=<file>)
#  reads {"queues":[...],"messages":{queue:[{priority,subject}]}} so the
#  logic is hermetically testable — see tests/test_bus_inbox_survey.py.
#
#  Exit codes:
#    0  survey ran (see RESULT line for actionable / clean)
#    1  could not reach the bus API (check failed to verify)
#
#  Prints one line per problem; RESULT: clean when nothing is actionable.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

BUS_BASE="${CORTEX_BUS_LOCAL_URL:-http://127.0.0.1:8903}"
ENV_FILE="${HOME}/hermes-cortex/.env"

if [[ -z "${BUS_SURVEY_FIXTURE:-}" && -z "${CORTEX_BUS_TOKEN:-}" && -r "$ENV_FILE" ]]; then
    # read token without echoing it
    CORTEX_BUS_TOKEN="$(grep -m1 '^CORTEX_BUS_TOKEN=' "$ENV_FILE" | cut -d= -f2- | tr -d '"'"'"' ')"
fi
export CORTEX_BUS_TOKEN BUS_BASE

python3 - <<'PY'
import os, sys, json, urllib.request, datetime

base = os.environ["BUS_BASE"]
fixture = os.environ.get("BUS_SURVEY_FIXTURE", "")

def http(path):
    req = urllib.request.Request(
        base + path,
        headers={"Authorization": "Bearer " + os.environ.get("CORTEX_BUS_TOKEN", "")})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)

if fixture:
    data = json.load(open(fixture))
    queues = data.get("queues", [])
    messages = data.get("messages", {})
else:
    try:
        queues = http("/api/pgmq/queues").get("queues", [])
    except Exception as e:
        print("FAIL: bus API unreachable at %s (%s)" % (base, e), file=sys.stderr)
        sys.exit(1)
    messages = {}
    for q in queues:
        if q.get("dlq") or not (q.get("depth", 0) or q.get("processing", 0)):
            continue
        try:
            messages[q["name"]] = http("/api/pgmq/peek/%s?limit=50" % q["name"]).get("messages", [])
        except Exception as e:
            print("FAIL: peek failed for queue %s (%s)" % (q["name"], e), file=sys.stderr)
            sys.exit(1)

PRIORITY_STR = {"normal": 0, "urgent": 10, "critical": 20}

def as_priority(p):
    if isinstance(p, str):
        return PRIORITY_STR.get(p.strip().lower(), 0)
    if isinstance(p, (int, float)):
        return int(p)
    return 0

active = [q for q in queues if q.get("depth", 0) or q.get("processing", 0)]
dlq = [q for q in queues if q.get("dlq") and (q.get("depth", 0) or q.get("processing", 0))]
blocked = [q for q in queues if q["name"] == "workflow_step_result"
           and (q.get("depth", 0) or q.get("processing", 0))]

urgent = []
for q in active:
    if q.get("dlq"):
        continue
    for m in messages.get(q["name"], []):
        p = as_priority(m.get("priority", 0))
        if p >= 20:
            urgent.append((q["name"], "critical", m.get("subject", "?")))
        elif p >= 10:
            urgent.append((q["name"], "urgent", m.get("subject", "?")))

for q in active:
    print("pending: %s depth=%s processing=%s" % (q["name"], q["depth"], q["processing"]))
for q in dlq:
    print("DLQ:     %s depth=%s processing=%s" % (q["name"], q["depth"], q["processing"]))
for q in blocked:
    print("BLOCKED: workflow_step_result depth=%s processing=%s" % (q["depth"], q["processing"]))
for qname, level, subject in urgent:
    print("%s: %s subject=%s" % (level.upper(), qname, subject))

actionable = bool(dlq or blocked or urgent)
now = datetime.datetime.now(datetime.timezone.utc)
print("RESULT: %s (active_queues=%d dlq=%d blocked=%d urgent=%d checked_at=%s)" % (
    "actionable" if actionable else "clean",
    len(active), len(dlq), len(blocked), len(urgent),
    now.isoformat(timespec="seconds")))
PY
