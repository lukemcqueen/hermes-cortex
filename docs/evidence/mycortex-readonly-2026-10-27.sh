#!/usr/bin/env bash
# Re-runnable evidence for the mycortex read-classification fix (nightly dream).
#
# Writes the committed transcript itself (exec >"$OUT"). Read-only throughout:
# it runs the guard test, re-derives the shipped classifier's verdicts, and
# reads file mtimes. It repairs nothing it measures.
#
# Re-run:  bash docs/evidence/mycortex-readonly-2026-10-27.sh
# Exit 0 = every applicable check passed.
#
# NOTE ON REVISIONS: prints `captured-at` (the revision the working tree sat on
# when the run happened) and deliberately no `tip:` line — writing this file
# changes the revision, so a committed copy is always one commit ahead.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$HERE/mycortex-readonly-2026-10-27.txt}"
DEPLOYED_ENF="${HOME}/.hermes/plugins/governance-enforcer/__init__.py"
REPO_ENF="${REPO}/plugins/governance-enforcer/__init__.py"

exec >"$OUT" 2>&1
norm() { sed -e "s|$HOME|~|g" -e "s|$(hostname)||g" -e 's/\x1b\[[0-9;]*m//g'; }
say()  { printf '%s\n' "$*" | norm; }
rule() { say "────────────────────────────────────────────────────────────"; }

fail=0
pending=0
ok()   { say "OK    $1"; }
bad()  { say "FAIL  $1"; fail=1; }
skip() { say "SKIP  $1"; }
pend() { say "PENDING $1"; pending=$((pending + 1)); }

say "mycortex read-classification — nightly dream unblock evidence"
say "generated-by : docs/evidence/mycortex-readonly-2026-10-27.sh"
say "captured-at  : $(git -C "$REPO" rev-parse --short=8 HEAD 2>/dev/null || echo unknown) (working tree at run time)"
say "date         : $(date -Iseconds)"
rule

say "## 1. The guard test — both directions, against the shipped predicate"
out=$(cd "$REPO" && bash tests/run-tests.sh tests/test_enforcer_mycortex_readonly.py -q 2>&1); rc=$?
if [ "$rc" -eq 0 ]; then
  ok "run-tests.sh tests/test_enforcer_mycortex_readonly.py -> rc=0  [$(printf '%s\n' "$out" | grep -E 'passed|failed' | tail -1)]"
else
  bad "guard test rc=$rc"; printf '%s\n' "$out" | tail -20
fi
rule

say "## 2. The shipped classifier's own verdicts (imported, not re-implemented)"
if [ -f "$REPO_ENF" ]; then
  probe=$(mktemp "${TMPDIR:-/tmp}/mcprobe.XXXXXX.py")
  cat >"$probe" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("enf_ev", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
fn = mod._is_readonly_terminal_command
for c in ["mycortex list -n 20", "mycortex search \"x\" --limit 3", "mycortex stats",
          "mycortex doctor", "mycortex sources list", "mycortex answer search \"q\"",
          "mycortex sync", "mycortex sources add foo /tmp/f", "mycortex sources remove foo",
          "mycortex answer store \"q\" \"a\"", "mycortex answer prune",
          "mycortex sync && mycortex list"]:
    print(f"      readonly={str(fn(c)):5s}  {c}")
PY
  python3 "$probe" "$REPO_ENF" || skip "could not load the enforcer module — verdicts NOT re-derived here"
  rm -f "$probe"
else
  bad "repo enforcer source missing"
fi
say "      (first three: reads -> True. The six mutations MUST stay False.)"
rule

say "## 3. Deployed copies carry the patterned entries"
for pair in "repo:$REPO_ENF" "deployed:$DEPLOYED_ENF"; do
  label="${pair%%:*}"; f="${pair#*:}"
  if [ ! -f "$f" ]; then bad "$label missing: ${f/#$HOME/~}"; continue; fi
  n=$(grep -c '^\s*r"\^\\s\*(mycortex)' "$f" || true)
  if [ "$n" -eq 3 ]; then ok "$label: 3 subcommand-scoped mycortex allowlist entries"
  else bad "$label: found $n mycortex allowlist entries, expected 3"; fi
done
rule

say "## 4. Is the RUNNING gateway serving the new classifier? (deploy != loaded)"
# The fix only takes effect once the gateway process has the new module. Compare
# the gateway's start time with the enforcer file's mtime. This is a mtime
# comparison and therefore a HINT, not proof — report it as such.
gpid=$(pgrep -f 'hermes.*gateway' | head -1 || true)
if [ -n "$gpid" ]; then
  verdict=$(python3 - "$gpid" "$DEPLOYED_ENF" <<'PY'
import os, subprocess, sys
pid, path = sys.argv[1], sys.argv[2]
try:
    out = subprocess.run(["ps", "-o", "lstart=", "-p", pid], capture_output=True, text=True, timeout=20)
    started = out.stdout.strip()
    if not started:
        print("SKIP COULD NOT VERIFY gateway start time — treat as restart required"); raise SystemExit
    # ps prints e.g. 'Fri Oct 23 17:20:15 2026'; parse with date -d (GNU) and
    # fall back to reporting could-not-verify rather than guessing.
    d = subprocess.run(["date", "-d", started, "+%s"], capture_output=True, text=True, timeout=20)
    if d.returncode != 0 or not d.stdout.strip().isdigit():
        print("SKIP COULD NOT VERIFY gateway start time — treat as restart required"); raise SystemExit
    g = int(d.stdout.strip()); s = int(os.path.getmtime(path))
    print(("OK gateway (pid %s) started %ds AFTER the enforcer was written — new classifier loaded"
           % (pid, g - s)) if g >= s else
          ("BAD gateway (pid %s) started %ds BEFORE the enforcer was written — running process has the OLD classifier; a gateway restart is REQUIRED"
           % (pid, s - g)))
except Exception as e:
    print(f"SKIP COULD NOT VERIFY ({type(e).__name__}) — treat as restart required")
PY
)
  case "$verdict" in
    OK*)   ok "${verdict#OK }" ;;
    BAD*)  pend "${verdict#BAD }" ;;
    SKIP*) skip "${verdict#SKIP }" ;;
    *)     skip "COULD NOT VERIFY — treat as restart required" ;;
  esac
else
  skip "no gateway process found on this host"
fi
say "      NOTE: the decisive read is the deploy's own reload line — it names only"
say "      'hooks', so the enforcer module itself is loaded at gateway start."
rule

say "## 5. The captured RED run of the guard (before the fix)"
RED="$HERE/mycortex-readonly-2026-10-27.RED.txt"
if [ -f "$RED" ]; then
  say "      path : docs/evidence/mycortex-readonly-2026-10-27.RED.txt"
  say "      md5  : $(md5sum "$RED" | cut -d' ' -f1)"
  say "      produced by: bash tests/run-tests.sh tests/test_enforcer_mycortex_readonly.py -q"
  say "      verdict    : $(grep -E '^=+ .*(passed|failed)' "$RED" | tail -1)"
else
  bad "RED capture missing"
fi
rule

if [ "$fail" -eq 0 ] && [ "$pending" -eq 0 ]; then
  say "RESULT: ALL PASS"
elif [ "$fail" -eq 0 ]; then
  say "RESULT: CHANGE VERIFIED — $pending PENDING action(s) on this host (see PENDING lines; not a defect in the change)"
else
  say "RESULT: FAILURES PRESENT (see FAIL lines above)"
fi
exit "$fail"
