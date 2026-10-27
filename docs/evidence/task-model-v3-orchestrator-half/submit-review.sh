#!/usr/bin/env bash
# Submit the row-9fb2ddb6 PLAN to the governed adversarial reviewer.
#
# The material is the plan document PLUS the raw measured capture, passed as
# CONTENT on argv (`--material`) — never as a file path, so the reviewer sees the
# whole plan rather than one string (the pitfall recorded in the orch-bus-worker
# skill). Run from the repo root, inside the governance cycle's lock:
#   bash docs/evidence/task-model-v3-orchestrator-half/submit-review.sh
set -u
cd "$(dirname "$0")/../../.." || exit 1

python3 - <<'PY'
import json, sqlite3, subprocess, sys
from pathlib import Path

REPO = Path.cwd()
HERE = REPO / "docs" / "evidence" / "task-model-v3-orchestrator-half"
CYCLE = 13847
REVIEWER_ID = "adv-review-cron-1954deb5ad76-13847"

plan = (REPO / "docs" / "design" / "task-model-v3-orchestrator-half.md").read_text()
capture = (HERE / "cur-surface.txt").read_text()
material = (
    plan
    + "\n\n=== RAW MEASURED CAPTURE (cur-surface.txt, tree 42b79528, host esther) ===\n"
    + capture
)
print(f"material bytes = {len(material)}")
rc = subprocess.call([
    sys.executable, str(REPO / "ops" / "scripts" / "orch-bus" / "adversarial-review.py"),
    "--cycle-id", str(CYCLE),
    "--material", material,
    "--review", "--reviewer-id", REVIEWER_ID,
])
print(f"reviewer rc = {rc}")

db = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"
conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row
try:
    row = conn.execute(
        "SELECT review_id, cycle_id, reviewer_model, verdict, summary, ts,"
        " findings_json FROM adversarial_reviews WHERE cycle_id = ?", (CYCLE,)
    ).fetchone()
finally:
    conn.close()
if row is None:
    print("NO REVIEW ROW RECORDED for cycle", CYCLE)
    sys.exit(1)
print(f"review_id       = {row['review_id']}")
print(f"reviewer_model  = {row['reviewer_model']}")
print(f"verdict         = {row['verdict']}")
print(f"ts              = {row['ts']}")
print("findings        = " + json.dumps(json.loads(row["findings_json"]), indent=2))
print("summary         = " + (row["summary"] or ""))
PY
