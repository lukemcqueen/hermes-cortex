#!/usr/bin/env python3
"""Service templates and shipped shell must work on macOS (bash 3.2, launchd) AND Linux.

Same family as the missing-venv break: a template that cannot start says nothing. Rules here:
no hardcoded /Users|/home in a template's STRING VALUES, $HOME in ProgramArguments only behind
/bin/bash -lc (launchd expands nothing), every plist parses, and the shell this repo ships for
other hosts avoids bash-4-only constructs. Launcher/venv rules: test_fleet_venv_launchers.py.

Run: python3 tests/test_fleet_templates.py
"""
import plistlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ABS_HOME = re.compile(r"/(?:home|Users)/[A-Za-z][A-Za-z0-9._-]*/")
SHIPPED_SHELL = [
    "ops/scripts/lib/require-fleet-venv.sh",
    "ops/scripts/lib/python-with-module.sh",
    "ops/scripts/manage/loop-gov-mcp.sh",
    "docs/evidence/verify-loop-gov-diagnosable.sh",
    "docs/evidence/verify-interpreter-choice.sh",
    "docs/evidence/verify-model-picker.sh",
]
BASH4 = [
    (re.compile(r"\bdeclare\s+-A\b"), "declare -A (bash 4+)"),
    (re.compile(r"\b(mapfile|readarray)\b"), "mapfile/readarray (bash 4+)"),
    (re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*,,|\$\{[A-Za-z_][A-Za-z0-9_]*\^\^"),
     "${var,,} case conversion (bash 4+)"),
    (re.compile(r"&>>"), "&>> redirect (bash 4+)"),
]


def _plists():
    return sorted((REPO / "docs" / "templates").glob("*.plist"))


def _no_comments(text):
    """Comment text EXPLAINS the rules and legitimately names /Users/luke; only the string
    values are code."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _argv(text):
    m = re.search(r"<key>ProgramArguments</key>\s*<array>(.*?)</array>", text, re.DOTALL)
    return re.findall(r"<string>(.*?)</string>", m.group(1), re.DOTALL) if m else []


def test_no_template_hardcodes_a_user_home():
    """A launchd template naming /Users/<someone>/ launches a dead path on every other Mac —
    and reads as PII. This is what missed Titus's plist until the pattern covered /Users/."""
    offenders = []
    for path in _plists():
        for line in _no_comments(path.read_text(errors="replace")).splitlines():
            if ABS_HOME.search(line):
                offenders.append(f"{path.name}: {line.strip()}")
    assert not offenders, f"hardcoded user home in a template: {offenders}"
    print("  no template hardcodes /Users/<name>/ or /home/<name>/ ✓")


def test_a_template_using_HOME_goes_through_a_shell():
    """launchd does NOT expand $HOME in plist strings. $HOME in ProgramArguments is valid only
    when the first argument is a shell that expands it — the dashboard template claimed
    launchd expanded it and the job could never start."""
    checked = 0
    for path in _plists():
        argv = _argv(_no_comments(path.read_text(errors="replace")))
        if not argv or "$HOME" not in " ".join(argv):
            continue
        checked += 1
        assert argv[0] in ("/bin/bash", "/bin/sh"), (
            f"{path.name} puts $HOME in ProgramArguments but execs {argv[0]!r} — launchd will "
            f"not expand it; use /bin/bash -lc")
    assert checked, "no template was inspected — the check is vacuous"
    print(f"  {checked} template(s) expand $HOME through a shell ✓")


def test_every_plist_template_parses():
    """A template launchd cannot parse is a service that never starts — an unescaped '&'
    (2>&1 inside XML) or a comment containing a double hyphen is how that happens."""
    checked = 0
    for path in _plists():
        try:
            data = plistlib.loads(path.read_bytes())
        except Exception as exc:
            raise AssertionError(f"{path.name} is not a parseable plist: {exc}") from None
        assert "Label" in data and (data.get("ProgramArguments") or []), path.name
        checked += 1
    assert checked, "no plist template was inspected — the check is vacuous"
    print(f"  {checked} plist template(s) parse, with a Label and ProgramArguments ✓")


def test_shipped_shell_is_bash_32_safe():
    """macOS ships bash 3.2 — Titus's host. declare -A / mapfile / ${var,,} die there with
    'invalid option' on a host we cannot test on. cortex-update.sh is excluded: it re-execs
    brew bash >= 4 by design."""
    checked = [(r, (REPO / r).read_text(errors="replace")) for r in SHIPPED_SHELL
               if (REPO / r).is_file()]
    assert checked, "no shipped shell inspected — the check is vacuous"
    offenders = []
    for rel, body in checked:
        for line in body.splitlines():
            if line.strip().startswith("#"):
                continue
            for rx, why in BASH4:
                if rx.search(line):
                    offenders.append(f"{rel}: {why}: {line.strip()}")
    assert not offenders, f"bash-4-only construct would break macOS: {offenders}"
    print(f"  {len(checked)} shipped shell file(s) are bash 3.2 safe ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
        except Exception:
            import traceback
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        return 1
    print(f"RESULT: ALL PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
