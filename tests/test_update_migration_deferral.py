#!/usr/bin/env python3
"""Regression test: a failing DB migration must not brick the enforcement sync.

Bug (Titus, 2026-10-01): `mycortex/migrate.py` failed because its Postgres
container was restarting (`psql: container is restarting`). Each migration did
`exit 1`, so the WHOLE update aborted at the migration step — which runs BEFORE
`deploy_governance_plugin()` and `install_precommit_hook()`. The enforcer plugin
was therefore never refreshed, DOGFOOD drift persisted, and the pre-commit gate
then blocked every repo on the host (the agent only needed a one-line commit in
an unrelated repo).

Root cause: a DB schema step (optional, retryable, dependent on external
infrastructure) could abort the critical enforcement sync.

The fix: migrations record into `_DEFERRED_FAILURES` and continue; the script
fails loudly with a non-zero exit AFTER the critical sync has completed.

Run: python3 -m pytest tests/test_update_migration_deferral.py -q
"""
import re
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_UPDATE = (_REPO / "ops" / "scripts" / "cortex-update.sh").read_text()
_LINES = _UPDATE.splitlines()

# The four schema migrations and the message each emits on failure.
_MIGRATIONS = [
    "mycortex migrate.py FAILED",
    "mycortex-mem migrate.py FAILED",
    "tasks migrate.py FAILED",
    "learnings migrate.py FAILED",
]


def _block_after(msg: str, span: int = 4) -> str:
    """The lines following a migration's failure message."""
    for i, line in enumerate(_LINES):
        if msg in line:
            return "\n".join(_LINES[i:i + span])
    raise AssertionError(f"failure message not found: {msg}")


# ── Structural: every migration defers, none exits ────────────

def test_no_migration_hard_exits_the_update():
    offenders = [m for m in _MIGRATIONS if "exit 1" in _block_after(m)]
    assert not offenders, (
        "these migrations still `exit 1`, aborting the critical enforcement "
        f"sync: {offenders}")


def test_every_migration_defers_its_failure():
    missing = [m for m in _MIGRATIONS if "_DEFERRED_FAILURES+=" not in _block_after(m)]
    assert not missing, f"migrations that do not defer their failure: {missing}"


def test_deferred_failures_are_reported_with_a_nonzero_exit():
    """The end-of-run check must exist and exit non-zero (no silent green)."""
    m = re.search(r"if \[\[ \$\{#_DEFERRED_FAILURES\[@\]\} -gt 0 \]\]; then(.*?)\n  fi",
                  _UPDATE, re.S)
    assert m, "end-of-run deferred-failure check not found"
    body = m.group(1)
    assert "exit 1" in body, "deferred failures must still exit non-zero"
    assert "_DEFERRED_FAILURES[@]" in body and "• " in body, (
        "the check must enumerate the failed migrations")


def test_deferred_check_runs_after_the_critical_sync():
    """It must come after the enforcer plugin + hook deploy, not before."""
    defer = _UPDATE.index("if [[ ${#_DEFERRED_FAILURES[@]} -gt 0 ]]")
    enforcer = _UPDATE.index("deploy_governance_plugin\n")
    hook = _UPDATE.index("  install_precommit_hook\n")
    assert defer > enforcer and defer > hook, (
        "the deferred check must run AFTER the enforcement chain is deployed")


# ── Real behavior: run the actual patterns ────────────────────

def test_deferred_pattern_continues_then_fails():
    """Executing the real defer dictum: control continues, exit is non-zero."""
    script = """
set -euo pipefail
_DEFERRED_FAILURES=()
error() { echo "ERR: $*" >&2; }
# mimic a migration block whose runner failed
if python3 -c 'raise SystemExit(1)' 2>/dev/null; then
  : # ok
else
  error "mycortex migrate.py FAILED"
  _DEFERRED_FAILURES+=("mycortex schema")
fi
echo "CRITICAL_SYNC_REACHED"
if [[ ${#_DEFERRED_FAILURES[@]} -gt 0 ]]; then
  error "deferred failures: ${_DEFERRED_FAILURES[*]}"
  exit 1
fi
"""
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert "CRITICAL_SYNC_REACHED" in r.stdout, (
        "control flow must continue past a failed migration")
    assert r.returncode == 1, "a deferred failure must still exit non-zero"
    assert "mycortex schema" in r.stderr, "the failure must be reported"


def test_old_hard_exit_pattern_is_gone():
    """No migration failure message is immediately followed by `exit 1`."""
    for msg in _MIGRATIONS:
        i = next(i for i, l in enumerate(_LINES) if msg in l)
        assert "exit 1" not in _LINES[i + 1], (
            f"{msg} is still immediately followed by exit 1")
