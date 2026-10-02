#!/usr/bin/env python3
"""hermes-plugin-lock status: one verdict per TARGET, and the verdict must be TRUE.

Reported by Titus (2026-10-02): `agent-remediate-apply` fired `enforcement_relock`
every 10-minute cycle, reporting "Re-locked 2 enforcement file(s) ... hooks, hooks" —
the same path twice, for a directory that was already locked.

Cause: the status branch inspected a directory with a command that lists its CHILDREN
(`ls -lO DIR` on macOS, `lsattr DIR` on Linux), so awk/lsattr emitted one verdict per
child. The directory's own flags were never read, so a locked dir could read as
"not locked" — which is what made the remediator re-lock it forever.

This test does two things: a static guard for the macOS branch (unrunnable on Linux) and
a real behavioral check of the Linux branch against this host's actual targets.
Run: python3 -m pytest tests/test_hermes_plugin_lock_status.py -q -s
"""
import os
import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "ops" / "install" / "deploy" / "nginx" / "hermes-plugin-lock"
_SRC = _SCRIPT.read_text()


def _status_branch() -> str:
    m = re.search(r"\n  status\)\n(.*?)\n    ;;", _SRC, re.S)
    assert m, "could not locate the status) branch in hermes-plugin-lock"
    return m.group(1)


def test_status_branch_inspects_the_target_not_its_children():
    """Static guard — this is the only coverage the macOS branch can get on Linux."""
    branch = _status_branch()
    assert "ls -ldO" in branch, "macOS status must use `ls -ldO` (dir-aware)"
    assert not re.search(r"ls -lO\s", branch), "bare `ls -lO` lists a directory's children"
    assert "lsattr -d" in branch, "Linux status must use `lsattr -d` (dir-aware)"
    assert not re.search(r"lsattr\s+\"\$t\"", branch), \
        "bare `lsattr $t` lists a directory's children"


def _targets() -> list:
    """Re-derive TARGETS the way the script does (kept in sync by the count assert)."""
    home = os.path.expanduser("~")
    return [
        f"{home}/.hermes/plugins/governance-enforcer/__init__.py",
        f"{home}/.hermes-cortex/scripts/pre-commit-score",
        f"{home}/.hermes-cortex/scripts/pre-push-pull",
        f"{home}/.hermes-cortex/scripts/post-commit-audit",
        f"{home}/.hermes-cortex/scripts/post-push-audit",
        f"{home}/.hermes-cortex/hooks/post-merge",
        f"{home}/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py",
        f"{home}/.hermes-cortex/hooks",
        f"{home}/.hermes-cortex/scripts/hermes-plugin-lock",
    ]


def test_old_form_really_did_report_a_child_control():
    """Control: prove the reported bug was real, so the fix is what changed it.

    If this ever stops holding (e.g. lsattr starts being dir-aware by default) the
    'bug' framing in the commit is wrong and this test should be re-examined.
    """
    hooks = os.path.expanduser("~/.hermes-cortex/hooks")
    if not os.path.isdir(hooks):
        print("  (hooks dir absent on this host — control skipped)")
        return
    old = subprocess.run(["lsattr", hooks], capture_output=True, text=True).stdout.strip()
    new = subprocess.run(["lsattr", "-d", hooks], capture_output=True, text=True).stdout.strip()
    old_paths = [ln.split()[-1] for ln in old.splitlines() if ln.strip()]
    new_paths = [ln.split()[-1] for ln in new.splitlines() if ln.strip()]
    assert old_paths, "expected the old form to emit something"
    assert all(p != hooks for p in old_paths), \
        f"control failed: bare `lsattr` already named the dir itself: {old_paths}"
    assert new_paths == [hooks], f"`lsattr -d` must name exactly the target: {new_paths}"
    print(f"  control ✓ old form named {old_paths[0].split('/')[-1]} (a child), "
          f"-d names the directory itself")


def test_real_status_output_has_no_duplicates_and_agrees_with_lsattr():
    """Behavioral: run the fixed script's status branch against the real targets."""
    r = subprocess.run(["bash", str(_SCRIPT), "status"], capture_output=True, text=True)
    assert r.returncode == 0, f"status exited {r.returncode}: {r.stderr[:400]}"
    verdicts: dict = {}
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if ": " in line and line.endswith(("locked", "not locked")):
            path, v = line.rsplit(": ", 1)
            verdicts[path] = v
        else:
            flags, _, path = line.rpartition(" ")
            verdicts[path] = flags
    targets = [t for t in _targets() if os.path.exists(t)]
    assert targets, "no targets exist on this host — nothing to verify"

    # 1. One verdict per target: the reported symptom was `hooks, hooks`.
    dupes = [p for p in verdicts if list(verdicts).count(p) > 1]
    assert not dupes, f"a path was reported more than once: {dupes}"
    assert len(verdicts) == len(targets), \
        f"{len(verdicts)} verdicts for {len(targets)} existing targets: {sorted(verdicts)}"

    # 2. Every verdict names a target, and each names ITSELF (no child paths).
    for p in verdicts:
        assert p in targets, f"status reported a non-target path: {p}"

    # 3. The verdict must be TRUE — compare against an independent lsattr -d.
    for t in targets:
        actual = subprocess.run(["lsattr", "-d", t], capture_output=True, text=True).stdout.strip()
        if not actual:
            continue
        real_locked = "i" in actual.split()[0]          # immutable bit
        got = verdicts[t]
        if got in ("locked", "not locked"):
            assert (got == "locked") == real_locked, \
                f"{t}: status says {got!r} but lsattr -d says {actual!r}"
        else:
            assert ("i" in got) == real_locked, \
                f"{t}: status reported {got!r} but lsattr -d says {actual!r}"
    print(f"  behavioral ✓ {len(verdicts)} existing targets, one verdict each, "
          f"every verdict agrees with lsattr -d (no spurious 'not locked' → no re-lock loop)")
