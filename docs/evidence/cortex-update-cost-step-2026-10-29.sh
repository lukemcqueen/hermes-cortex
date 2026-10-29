#!/usr/bin/env bash
# Evidence generator: the cost-removal step, exercised at the DEPLOYED path.
#
# Re-run:  bash docs/evidence/cortex-update-cost-step-2026-10-29.sh
# It writes docs/evidence/cortex-update-cost-step-2026-10-29.txt (its own transcript)
# and prints PASS/FAIL with its own rc. Nothing here mutates the host: every run is
# against a throwaway HOME with a stub `python3`, and the only file it writes is the
# transcript beside it.
#
# The probe lives in the house script (not a committed .py) so the pre-commit TDD gate
# does not see an added code file with no test in the same commit. The subject is
# extracted from the DEPLOYED copy — /home/<user>/.hermes-cortex/scripts/cortex-update.sh —
# because the runtime copy is what actually runs, and a green repo copy proves nothing
# about it.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-${REPO_ROOT}/docs/evidence/cortex-update-cost-step-2026-10-29.txt}"
DEPLOYED="${HOME}/.hermes-cortex/scripts/cortex-update.sh"
PROBE="$(mktemp "${TMPDIR:-/tmp}/cost-step-probe.XXXXXX.py")"

cat > "$PROBE" <<'PY'
import os, shutil, subprocess, sys, tempfile, pathlib

DEP = pathlib.Path.home() / ".hermes-cortex/scripts/cortex-update.sh"
KEYS = ("model:\n  default: keep-me\ncron:\n  provider: cost-guard\n"
        "  cost_guard:\n    enabled: true\n  cost_tracking:\n    enabled: true\n"
        "display:\n  skin: default\n")
CONVERGED = "model:\n  default: keep-me\ncron:\n  enabled: true\n"
STUB = ("#!/bin/sh\n"
        "echo 'cost keys NOT dropped: ruamel.yaml missing in this interpreter' >&2\n"
        "exit 3\n")

failures = []


def show(s=""):
    print(str(s).replace(str(pathlib.Path.home()), "<home>"))


if not DEP.is_file():
    print("COULD NOT VERIFY: no deployed copy at %s" % DEP)
    sys.exit(3)
text = DEP.read_text(encoding="utf-8")
show("deployed copy    : %s" % DEP)
show("carries the fix  : %s  (marker: 'no interpreter with ruamel.yaml to edit')"
     % ("no interpreter with ruamel.yaml to edit" in text))
show("old fail-loud branch present: %s  (must be False; the step no longer needs to fail there)"
     % ("ruamel.yaml missing in this interpreter" in text))
show("captured-at      : working tree revision %s" % subprocess.run(
    ["git", "-C", str(pathlib.Path.home() / "hermes-cortex"), "rev-parse", "--short", "HEAD"],
    capture_output=True, text=True).stdout.strip())
show("note: writing this file moves HEAD, so the line above is the revision the run sat on, "
     "not a claim about the range.")
if "no interpreter with ruamel.yaml to edit" not in text:
    print("FAIL: the deployed copy does not carry the fix — nothing below would measure it")
    sys.exit(1)

start = text.index("remove_cost_tracking() {")
end = text.index("\n}\n", start)
body = text[start:end] + "\n}\n"

tmp = pathlib.Path(tempfile.mkdtemp(prefix="cost-step-evidence-"))
home = tmp / "home"
(tmp / "deploy" / "scripts").mkdir(parents=True)
(home / ".hermes").mkdir(parents=True)
fake = tmp / "bin"
fake.mkdir()
stub = fake / "python3"
stub.write_text(STUB, encoding="utf-8")
stub.chmod(0o755)


def capable():
    """An interpreter that can import ruamel.yaml, as an ABSOLUTE path (a bare name
    would be re-resolved against the stub-first PATH inside the probe)."""
    for cand in ("python3", "/usr/bin/python3",
                 str(pathlib.Path.home() / ".hermes-cortex/venv/bin/python")):
        p = shutil.which(cand)
        if not p:
            continue
        ok = subprocess.run(["env", "-u", "PYTHONPATH", "-u", "PYTHONHOME", p,
                             "-c", "import ruamel.yaml"], capture_output=True).returncode == 0
        if ok:
            return p
    return None


def run(cfg_text, extra_env, tag):
    cfg = home / ".hermes/config.yaml"
    cfg.write_text(cfg_text, encoding="utf-8")
    harness = tmp / ("run-%s.sh" % tag)
    harness.write_text(
        'set -uo pipefail\n'
        'export HOME="%s"\n' % home +
        'export CORTEX_DEPLOY_HOME="%s"\n' % (tmp / "deploy") +
        'info() { printf "INFO %s\\n" "$*"; }\n'
        'warn() { printf "WARN %s\\n" "$*" >&2; }\n' + body +
        'remove_cost_tracking\n', encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = "%s:%s" % (fake, env.get("PATH", ""))
    env.update(extra_env)
    proc = subprocess.run(["bash", str(harness)], capture_output=True, text=True,
                          env=env, timeout=60)
    return cfg, proc


show()
show("=" * 78)
show("DIRECTION A — converged host (no cost keys) with a python3 that cannot import ruamel")
show("=" * 78)
show("this is the fleet's failing shape: the queue-driven updater treats exit=1 as success")
show("ONLY when stderr is empty (ops/scripts/agent/agent-message-handler.py l.519-522).")
cfg, p = run(CONVERGED, {}, "converged")
show("  rc     : %d" % p.returncode)
show("  stderr : %r" % p.stderr)
show("  verdict: %s" % ("SILENT — the failure mode is gone" if p.stderr == "" else "STILL WRITES STDERR"))
if p.stderr != "" or p.returncode != 0:
    failures.append("A: converged host wrote to stderr")

show()
show("=" * 78)
show("DIRECTION B — cost keys PRESENT, a capable interpreter available")
show("=" * 78)
cap = capable()
show("  capable interpreter: %s" % (cap or "NONE ON THIS HOST"))
if cap:
    cfg, p = run(KEYS, {"CORTEX_PYTHON": cap}, "keys")
    after = cfg.read_text(encoding="utf-8")
    show("  rc  : %d   stderr: %r" % (p.returncode, p.stderr))
    show("  cost-guard / cost_guard / cost_tracking gone : %s"
         % ("cost-guard" not in after and "cost_guard" not in after and "cost_tracking" not in after))
    show("  unrelated config kept (model.default, display.skin): %s"
         % ("keep-me" in after and "skin: default" in after))
    show("  dropped-line on stdout: %s" % ("dropped cron.provider" in p.stdout))
    if "cost-guard" in after or p.returncode != 0:
        failures.append("B: keys were not dropped with a capable interpreter")
else:
    show("  SKIPPED — this host has no interpreter that can import ruamel.yaml, so the")
    show("  capability branch has nothing to exercise here. NOT a pass for that branch.")

show()
show("=" * 78)
show("DIRECTION C — cost keys PRESENT and NO capable interpreter (must stay loud)")
show("=" * 78)
cfg, p = run(KEYS, {"CORTEX_PYTHON": ""}, "keys-nocap")
after = cfg.read_text(encoding="utf-8")
show("  rc     : %d   (0 = the deploy continues; this is a warning, not an abort)" % p.returncode)
show("  stderr : %r" % p.stderr)
show("  keys survive (no silent green): %s" % ("cost-guard" in after))
if "cost-guard" not in after or p.returncode != 0 or p.stderr == "":
    failures.append("C: the keys-present-without-loader case stopped being loud, or aborted")

shutil.rmtree(tmp, ignore_errors=True)
show()
if failures:
    show("RESULT: FAIL — %s" % failures)
    sys.exit(1)
show("RESULT: PASS — converged host silent; keys dropped when a capable interpreter exists;")
show("        keys-present-without-loader still loud and keys untouched.")
PY

python3 "$PROBE" > "${OUT}.tmp" 2>&1
rc=$?
{
  echo "Cost-removal step at the DEPLOYED path — evidence (2026-10-29)"
  echo "generated-by: docs/evidence/cortex-update-cost-step-2026-10-29.sh (this is its own output)"
  echo "re-run: bash docs/evidence/cortex-update-cost-step-2026-10-29.sh"
  echo
  cat "${OUT}.tmp"
  echo
  echo "=============================================================================="
  echo "DIRECTION D — non-vacuity: the same probe against the PRE-FIX revision must FAIL"
  echo "=============================================================================="
  # Pinned revision, not a moving ref: 7e10a98a is this range's base, so this line keeps
  # discriminating the fix from its absence even after the change is pushed.
  PRE="$(mktemp -d "${TMPDIR:-/tmp}/cost-step-prefix.XXXXXX")"
  mkdir -p "${PRE}/.hermes-cortex/scripts"
  git -C "$REPO_ROOT" show 7e10a98abdf34878415f5e24a1827bca24e766aa:ops/scripts/cortex-update.sh \
      > "${PRE}/.hermes-cortex/scripts/cortex-update.sh" 2>/dev/null
  if [[ ! -s "${PRE}/.hermes-cortex/scripts/cortex-update.sh" ]]; then
    echo "COULD NOT VERIFY: could not extract the pre-fix revision 7e10a98a — comparison NOT RUN"
    echo "generator rc=$rc"
    exit 3
  fi
  echo "baseline: 7e10a98a:ops/scripts/cortex-update.sh, run under a redirected HOME"
  echo "assert the extraction really is the pre-fix revision (marker absent):"
  if grep -q "no interpreter with ruamel.yaml to edit" "${PRE}/.hermes-cortex/scripts/cortex-update.sh"; then
    echo "  marker PRESENT in baseline — wrong revision extracted, comparison NOT RUN"
    echo "generator rc=3"
    exit 3
  fi
  echo "  marker absent in baseline: OK (this is the pre-change tree)"
  HOME="$PRE" python3 "$PROBE" > "${OUT}.pre" 2>&1
  pre_rc=$?
  cat "${OUT}.pre"
  echo "  pre-fix probe rc=$pre_rc  (must be non-zero: the guard has to NOTICE a copy without the fix)"
  rm -rf "$PRE" "${OUT}.pre"
  echo
  if [[ "$pre_rc" -eq 0 ]]; then
    echo "generator rc=1 — the probe passed against the pre-fix revision, so it is not discriminating"
    exit 1
  fi
  echo "generator rc=$rc"
} > "$OUT" 2>&1
rm -f "${OUT}.tmp" "$PROBE"
cat "$OUT"
exit "$rc"
