#!/usr/bin/env bash
# [cost/4] deployed-path check — run AFTER cortex-dogfood.sh has deployed.
#
#   bash ops/evidence/cost4-host-cost-adapter-deploy-2026-10-24.sh
#
# Writes docs/evidence/cost4-host-cost-adapter/deployed-check.txt. This is a
# separate artifact from verify.txt because it can only be true after the
# deploy, and the deploy is the LAST step before the push — folding it into the
# pre-deploy transcript would make that transcript claim a state it never saw.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTDIR="$REPO/docs/evidence/cost4-host-cost-adapter"
OUT="$OUTDIR/deployed-check.txt"
PY="$HOME/.hermes-cortex/venv/bin/python3"
REL="ops/scripts/manage/cron-cost-metrics.py"
DEPLOYED="$HOME/.hermes-cortex/scripts/cron-cost-metrics.py"
SCRATCH="$(mktemp -d "$HOME/.hermes/cache/scratch/cost4-dep-XXXXXX")"

mkdir -p "$OUTDIR"
exec >"$OUT" 2>&1

say() { printf '%s\n' "$*" | sed -e "s|$HOME|~|g"; }
rule() { printf '\n%s\n' "── $* ──"; }

say "# [cost/4] deployed-path check"
say "captured-at: $(git -C "$REPO" rev-parse --short=8 HEAD)"
say "re-run: bash ops/evidence/cost4-host-cost-adapter-deploy-2026-10-24.sh"

rule "1. the DEPLOYED copy is the repo copy, modulo the deploy banner"
say "\$ cmp after stripping leading comment/blank lines on BOTH sides"
"$PY" - "$REPO/$REL" "$DEPLOYED" <<'PYEOF'
import hashlib, sys
from pathlib import Path

def body(path):
    lines = Path(path).read_text().splitlines()
    # The deploy adds `# SOURCE:` / `# Do NOT edit` lines and its own shape
    # varies per file type, so strip leading comment/blank lines on BOTH sides
    # rather than a fixed line count (a fixed `sed 1,3d` can eat a shebang and
    # report drift that does not exist).
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    return "\n".join(lines)

repo_path, deployed_path = sys.argv[1], sys.argv[2]
repo_body, dep_body = body(repo_path), body(deployed_path)
print("repo      :", repo_path.replace(str(Path.home()), "~"),
      hashlib.sha256(repo_body.encode()).hexdigest()[:16])
print("deployed  :", deployed_path.replace(str(Path.home()), "~"),
      hashlib.sha256(dep_body.encode()).hexdigest()[:16])
same = repo_body == dep_body
print("identical modulo the banner:", same)
print("carries the change (--json-summary present):",
      "--json-summary" in dep_body)
sys.exit(0 if same else 1)
PYEOF
say "rc=$? (0 = the running copy IS this change)"

rule "2. the DEPLOYED copy, --json-summary, on this host's live log"
say "\$ python3 ~/.hermes-cortex/scripts/cron-cost-metrics.py --json-summary --since 2026-10-06"
"$PY" "$DEPLOYED" --json-summary --since 2026-10-06 >"$SCRATCH/dep.json" 2>"$SCRATCH/dep.err"
say "rc=$?"
say "stderr bytes: $(wc -c < "$SCRATCH/dep.err")   stdout bytes: $(wc -c < "$SCRATCH/dep.json")"
"$PY" - "$SCRATCH/dep.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
print("agent     :", d["agent"])
print("rows      :", d["audit"]["rows"], "skipped:", d["audit"]["skipped_rows"])
print("per_day   :", len(d["per_day"]), "days, last:", d["per_day"][-1])
print("per_job   :", len(d["per_job"]), "rows (omitted", d["per_job_omitted"], "), top:",
      d["per_job"][0]["job_id"], d["per_job"][0]["fires"], "fires")
print("spend     : available", d["spend"]["available"])
print("langfuse  :", {k: v for k, v in d["langfuse"].items() if k != "days"})
PYEOF

rule "3. the UNIVERSAL producer path is unchanged — --prometheus still emits"
say "\$ python3 <deployed> --prometheus --agent <agent>   (what agent-push-metrics.sh calls)"
"$PY" "$DEPLOYED" --prometheus >"$SCRATCH/prom.txt" 2>"$SCRATCH/prom.err"
say "rc=$?"
say "series bytes: $(wc -c < "$SCRATCH/prom.txt")   stderr bytes: $(wc -c < "$SCRATCH/prom.err")"
say "tokens_total lines: $(grep -c 'hermes_cron_tokens_total' "$SCRATCH/prom.txt")"
say "cost_available line: $(grep 'hermes_cron_cost_available{' "$SCRATCH/prom.txt")"

say ""
say "# generated-by: this script (it wrote this file itself; stdout is not retyped)"
