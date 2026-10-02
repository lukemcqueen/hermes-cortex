#!/usr/bin/env python3
"""A retired cron must be removed on EVERY surface — and stay removed.

Regression (Luke, 2026-10-02: "why do we still see these? Please remove them as
they are done: cron:orch-task-board-digest"). The job was gone from jobs.json and
from every cron listing, yet kept firing daily: it ran from a SYSTEMD TIMER the
cron-bridge generator had created, and the generator has no prune step.

This pins the removal of `orch-task-board-digest` and, more importantly, the
INTENTIONAL asymmetry that makes it stick:

  * no create_cron block  -> the installer never recreates the job
  * STILL in the uninstall array -> every host that still carries it removes it
  * no cron-manifest entry -> the manifest check does not expect it
  * the installer stays syntactically valid (a comment placed inside a
    backslash-continued list swallows the continuation and breaks the script —
    hit for real while making this change)

Run: python3 -m pytest tests/test_retired_orch_crons.py -q
"""
import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_INSTALLER = _REPO / "ops" / "scripts" / "install" / "install-orch-crons.sh"
_MANIFEST = _REPO / "ops" / "install" / "cron-manifest.yaml"

RETIRED = "orch-task-board-digest"


def _text(path: Path) -> str:
    return path.read_text()


def test_the_retired_cron_has_no_create_block():
    """Nothing recreates it: a create_cron block would re-arm the job."""
    body = _text(_INSTALLER)
    assert f'create_cron "{RETIRED}"' not in body, (
        f"{RETIRED} still has a create_cron block — the next install recreates the job")


def test_the_retired_cron_stays_in_the_uninstall_array():
    """The asymmetry is deliberate: this entry is what removes it on other hosts.

    Removing it here would leave the job running on every host that still has it.
    """
    body = _text(_INSTALLER)
    assert f'"{RETIRED}"' in body, (
        f"{RETIRED} is missing from the uninstall array — hosts that still carry the "
        "job would never clean it up")


def test_the_retired_cron_is_absent_from_the_manifest():
    assert f"- name: {RETIRED}" not in _text(_MANIFEST), (
        f"{RETIRED} is still in cron-manifest.yaml — the manifest check will expect it")


def test_the_installer_is_syntactically_valid():
    """Runnable proof that the edited installer still parses."""
    r = subprocess.run(["bash", "-n", str(_INSTALLER)], capture_output=True, text=True)
    assert r.returncode == 0, f"bash -n failed:\n{r.stdout}\n{r.stderr}"


def test_the_manifest_check_accepts_the_retirement():
    """Runnable proof that dropping the manifest entry keeps the check green."""
    r = subprocess.run(
        [sys.executable, str(_REPO / "ops" / "scripts" / "manage" / "cron_manifest.py"), "--check"],
        capture_output=True, text=True, cwd=str(_REPO))
    assert r.returncode == 0, f"cron_manifest.py --check failed:\n{r.stdout}\n{r.stderr}"
    assert "OK" in (r.stdout + r.stderr), r.stdout + r.stderr


def test_no_comment_inside_the_backslash_continued_uninstall_list():
    """Control for the bash pitfall: a comment inside the list breaks the script.

    The list is a backslash-continued `for job in \\` sequence; bash strips the
    continuation BEFORE comment processing, so `"a" \\` + `# note` + `"b"` becomes
    two commands and a syntax error.
    """
    lines = _text(_INSTALLER).splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip().startswith("for job in"))
    end = next(i for i in range(start, len(lines)) if lines[i].rstrip().endswith("; do"))
    for i in range(start + 1, end):
        assert not lines[i].strip().startswith("#"), (
            f"comment inside the uninstall list at line {i + 1} — this breaks the "
            "backslash continuation (put it above the `for` instead)")
