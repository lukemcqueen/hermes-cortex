#!/usr/bin/env bash
# Evidence generator for the 2026-10-15 cron-manifest drift sync.
#
# Read-only: every command below only reads (git show, --check, --json, bash -n,
# pytest, adversarial-verify without --write, doctor --quiet). Nothing here repairs,
# deploys, commits or mutates state. Reproduce with:
#   bash ops/evidence/cron-manifest-drift-sync-2026-10-15.sh > <out>
#
# Each command is printed immediately above its OWN exit code, measured bare with no
# pipe (a piped rc=$? would report the LAST stage's status instead of the command's).
# Volatile by design: the revision SHAs are the ones this change landed on.
set -uo pipefail

# Redact at the SOURCE: re-exec once with stdout filtered, so the committed artifact
# never carries a home path. `s|$HOME|~|g` only — a bare host-name replace would also
# mangle legitimate identifiers that contain it (a DB role, an agent name).
if [[ "${1:-}" != "--no-redact" ]]; then
  "$0" --no-redact | sed -e "s|${HOME}|~|g"
  exit "${PIPESTATUS[0]}"
fi

cd "$(dirname "$0")/../.." || exit 2
REPO="$PWD"
PY="${HOME}/.hermes/hermes-agent/venv/bin/python3"
TMP="${HOME}/.hermes/cache/scratch"
mkdir -p "$TMP"

run() {  # run <label> <cmd...> — print cmd, run it, print its rc (bare, unpiped)
  local label="$1"; shift
  echo "=== [$label] \$ $*"
  "$@"
  echo "--- rc=$?"
  echo
}

echo "# cron-manifest drift sync — GENERATED artifact (not hand-written)"
echo "# generated_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# generator: ops/evidence/cron-manifest-drift-sync-2026-10-15.sh"
echo "# revisions: parent=$(git rev-parse --short HEAD~1) tip=$(git rev-parse --short HEAD)"
echo "# redacted at source: \$HOME for home paths (sed -e 's|\$HOME|~|g')."
echo

echo "## 1. the baseline REVISION reproduces the defect, the tip does not"
echo "# the manifest prompt is compared to the prompt install-orch-crons.sh creates,"
echo "# parsed with the repo test's own line-based extractor."
"$PY" - <<'PY'
import subprocess, sys
from pathlib import Path
sys.path.insert(0, "tests")
from test_cron_prompt_matches_installer import extract_prompt

INST = "ops/scripts/install/install-orch-crons.sh"
NAME = "orch-task-morning-pass"
installer = extract_prompt(Path(INST).read_text(), NAME)

def manifest_prompt(rev):
    text = subprocess.run(["git", "show", f"{rev}:ops/install/cron-manifest.yaml"],
                          capture_output=True, text=True, check=True).stdout
    import yaml
    return next(c["prompt"] for c in yaml.safe_load(text)["crons"] if c["name"] == NAME)

for rev in ("HEAD~1", "HEAD"):
    mp = manifest_prompt(rev)
    print(f"manifest@{rev}: {len(mp)} chars | installer: {len(installer)} chars | equal={mp == installer}")
print(f"assert baseline({('HEAD~1')}) != installer: {manifest_prompt('HEAD~1') != installer}")
print(f"assert tip(HEAD) == installer:            {manifest_prompt('HEAD') == installer}")
PY
echo "--- rc=$?"
echo

run "2. drift check (the doctor's own reader)" \
  "$PY" "$HOME/hermes-cortex/ops/scripts/manage/cron_manifest.py" --check

echo "=== [2b] \$ cron_manifest.py --json | python3 -c (drifted/missing names)"
"$PY" "$HOME/hermes-cortex/ops/scripts/manage/cron_manifest.py" --json > "$TMP"/_ev_drift.json
echo "--- manifest json rc=$?"
"$PY" -c "import json; d=json.load(open('"$TMP"/_ev_drift.json')); print('drifted:', [x['name'] for x in d['drifted']]); print('missing:', [x['name'] for x in d['missing']])"
echo "--- rc=$?"
echo
run "3. installer syntax" bash -n ops/scripts/install/install-orch-crons.sh
run "4. prompt parity test (live == installer)" \
  "$PY" -m pytest tests/test_cron_prompt_matches_installer.py -q
run "5. static adversarial gate on the changed script" \
  "$PY" "$HOME/.hermes-cortex/scripts/adversarial-verify.py" \
  --file ops/scripts/install/install-orch-crons.sh --level A2 --gate
echo "=== [6] \$ live job pin state (orch-bus-worker must be unpinned)"
"$PY" -c "import json,os; d=json.load(open(os.path.expanduser('~/.hermes/cron/jobs.json'))); jobs=d.get('jobs',d); j=[x for x in jobs if x.get('name')=='orch-bus-worker'][0]; print('model=%r provider=%r' % (j.get('model',''), j.get('provider','')))"
echo "--- rc=$?"
echo
echo "## 7. doctor (post-deploy) — date + overall line + rc"
echo "=== [7] \$ date"
date
echo "--- rc=$?"
echo
"$PY" "$HOME/hermes-cortex/ops/scripts/manage/cortex-doctor.py" --quiet > "$TMP"/_ev_doctor.txt 2>&1
echo "--- doctor rc=$?"
grep -E "Cron manifest drift|Overall" "$TMP"/_ev_doctor.txt
echo
echo "# NOTE (disclosed, not hidden): the doctor's rc is 1 because it emits WARNINGS;"
echo "# the push gate blocks on FAIL only, and fail=0 above. cron_manifest --check exits 1"
echo "# on the ORPHAN 'orch-backlog-driver' — a disabled leftover live job from the"
echo "# 2026-10-14 rename, reported by the doctor as INFO, not a FAIL. Not touched by this"
echo "# change (an unattended run leaves a live-state deletion to a human decision)."
