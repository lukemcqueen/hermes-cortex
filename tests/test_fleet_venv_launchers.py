#!/usr/bin/env python3
"""No fleet launcher may bare-exec the fleet venv — the class, not the incident.

Kustos's loop-governance MCP died as bash's "line 11: No such file or directory". That was
one launcher; the wall is the same for every launcher, so the remedy has to be a rule rather
than a one-off patch. This sweep fails when:

  * a tracked file exec's the fleet venv WITHOUT going through the shared guard
    (scripts/lib/require-fleet-venv.sh), which names the missing piece and how to fix it;
  * a launcher hardcodes an absolute home, which breaks on every host whose user differs.

Adding a new launcher is fine — it must source the guard, like loop-gov-mcp.sh does.

Run: python3 tests/test_fleet_venv_launchers.py
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUARD = "ops/scripts/lib/require-fleet-venv.sh"
GUARD_MARKERS = ("require-fleet-venv.sh", "require_fleet_venv")
#: Files allowed to mention the venv in an exec line. Each needs a reason, not a shrug.
ALLOW = {
    GUARD,  # the guard itself is the one that MUST name the path
}
VENV_REF = re.compile(r"hermes-cortex/venv|fleet_venv_python|FLEET_VENV_DIR")
EXEC_LINE = re.compile(r"\bexec\b")
#: BOTH platform layouts. /Users/<name>/ was missing from this pattern, so the first run of
#: this test PASSED over a plist that hardcodes /Users/luke — a probe bug, not a clean file.
#: Check the probe before believing a green result.
ABS_HOME = re.compile(r"/(?:home|Users)/[A-Za-z][A-Za-z0-9._-]*/")
SKIP_SUFFIX = (".md", ".txt", ".json", ".yaml", ".yml", ".plist", ".raw")


def _tracked():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return [REPO / p for p in out.stdout.split() if p]


def _code_lines(path):
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            yield stripped


def test_no_launcher_execs_the_fleet_venv_without_the_guard():
    offenders = []
    for path in _tracked():
        rel = path.relative_to(REPO).as_posix()
        if rel in ALLOW or rel.endswith(SKIP_SUFFIX) or not path.is_file():
            continue
        body = path.read_text(errors="replace")
        if not VENV_REF.search(body):
            continue
        if not any(EXEC_LINE.search(line) and VENV_REF.search(line) for line in _code_lines(path)):
            continue          # mentions the venv but does not exec it
        if any(marker in body for marker in GUARD_MARKERS):
            continue          # goes through the guard
        offenders.append(rel)
    assert not offenders, (
        "these launchers exec the fleet venv without the shared guard "
        f"(source {GUARD} and call require_fleet_venv): {offenders}"
    )
    print("  every launcher that execs the fleet venv goes through the guard ✓")


def test_the_known_launcher_is_guarded():
    """Control: the sweep must be looking at something, not passing vacuously."""
    wrapper = REPO / "ops/scripts/manage/loop-gov-mcp.sh"
    body = wrapper.read_text()
    assert "require-fleet-venv.sh" in body, "loop-gov-mcp.sh must source the guard"
    assert "require_fleet_venv" in body, "and call it"
    print("  loop-gov-mcp.sh sources and calls the guard ✓")


def test_the_sweep_would_catch_a_bare_exec():
    """Prove the detector fires, so a green sweep means something."""
    sample = 'set -u\nexec "$HOME/.hermes-cortex/venv/bin/python3" "$HOME/.hermes-cortex/tools/x.py" "$@"\n'
    assert VENV_REF.search(sample) and any(
        EXEC_LINE.search(line) and VENV_REF.search(line) for line in sample.splitlines())
    assert not any(m in sample for m in GUARD_MARKERS), "a bare exec is exactly what it must flag"
    print("  a bare exec is detected as an offender ✓")


def test_no_absolute_home_in_launcher_code():
    """$HOME-resolved, always: an absolute path breaks on every other fleet host."""
    offenders = []
    for rel in ("ops/scripts/manage/loop-gov-mcp.sh", GUARD):
        for line in _code_lines(REPO / rel):
            if ABS_HOME.search(line):
                offenders.append(f"{rel}: {line}")
    assert not offenders, f"absolute home paths break other hosts: {offenders}"
    print("  no absolute home in launcher/guard code ✓")


def _strip_plist_comments(text):
    """Comment text explains the rules and legitimately names /Users/luke — only the
    STRING VALUES are code."""
    import re as _re
    return _re.sub(r"<!--.*?-->", "", text, flags=_re.DOTALL)


def _program_arguments(text):
    import re as _re
    m = _re.search(r"<key>ProgramArguments</key>\s*<array>(.*?)</array>", text, _re.DOTALL)
    return _re.findall(r"<string>(.*?)</string>", m.group(1), _re.DOTALL) if m else []


def test_no_template_hardcodes_a_user_home():
    """A launchd template with /Users/<someone>/ in it launches a dead path on every other
    Mac — and reads as PII. Comments may explain the rule; string values must not break it."""
    offenders = []
    for path in sorted((REPO / "docs" / "templates").glob("*.plist")):
        body = _strip_plist_comments(path.read_text(errors="replace"))
        for line in body.splitlines():
            if ABS_HOME.search(line):
                offenders.append(f"{path.name}: {line.strip()}")
    assert not offenders, f"hardcoded user home in a template: {offenders}"
    print("  no template hardcodes /Users/<name>/ or /home/<name>/ ✓")


def test_a_template_using_HOME_goes_through_a_shell():
    """launchd does NOT expand $HOME in plist strings. A $HOME in ProgramArguments is only
    valid when the first argument is a shell that will expand it — the dashboard template
    claimed launchd expanded it and the job could never start."""
    checked = 0
    for path in sorted((REPO / "docs" / "templates").glob("*.plist")):
        argv = _program_arguments(_strip_plist_comments(path.read_text(errors="replace")))
        if not argv or "$HOME" not in " ".join(argv):
            continue
        checked += 1
        assert argv[0] in ("/bin/bash", "/bin/sh"), (
            f"{path.name} puts $HOME in ProgramArguments but execs {argv[0]!r} — launchd will "
            f"not expand it; use /bin/bash -lc"
        )
    assert checked, "no template was inspected — the check is vacuous"
    print(f"  {checked} template(s) expand $HOME through a shell ✓")


def test_every_plist_template_parses():
    """A template launchd cannot parse is a service that never starts — and an unescaped '&'
    in a shell redirect (`2>&1` inside XML) is exactly how that happens. Caught here while
    rewriting the templates: all three were malformed."""
    import plistlib
    checked = 0
    for path in sorted((REPO / "docs" / "templates").glob("*.plist")):
        try:
            data = plistlib.loads(path.read_bytes())
        except Exception as exc:
            raise AssertionError(f"{path.name} is not a parseable plist: {exc}") from None
        assert "Label" in data, f"{path.name} has no Label"
        argv = data.get("ProgramArguments") or []
        assert argv, f"{path.name} has no ProgramArguments"
        checked += 1
    assert checked, "no plist template was inspected — the check is vacuous"
    print(f"  {checked} plist template(s) parse, with a Label and ProgramArguments ✓")


def _load_shipped_shell():
    """The shell this repo ships for OTHER hosts to run: launchers, the guard, verifiers.
    (cortex-update.sh is excluded — it re-execs brew bash >=4 on macOS by design.)"""
    rels = [
        "ops/scripts/lib/require-fleet-venv.sh",
        "ops/scripts/lib/python-with-module.sh",
        "ops/scripts/manage/loop-gov-mcp.sh",
        "docs/evidence/verify-loop-gov-diagnosable.sh",
        "docs/evidence/verify-interpreter-choice.sh",
        "docs/evidence/verify-model-picker.sh",
    ]
    return [(r, (REPO / r).read_text(errors="replace")) for r in rels if (REPO / r).is_file()]


def test_shipped_shell_is_bash_32_safe():
    """macOS ships bash 3.2 — Titus's host. A bash-4-only construct (declare -A, mapfile,
    ${var,,}) dies there with 'invalid option' or 'command not found' on a host we cannot
    test on. These files are meant to run anywhere, so they stay inside 3.2's language."""
    patterns = [
        (re.compile(r"\bdeclare\s+-A\b"), "declare -A (bash 4+)"),
        (re.compile(r"\b(mapfile|readarray)\b"), "mapfile/readarray (bash 4+)"),
        (re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*,,|\$\{[A-Za-z_][A-Za-z0-9_]*\^\^"),
         "${var,,} case conversion (bash 4+)"),
        (re.compile(r"&>>"), "&>> redirect (bash 4+)"),
    ]
    checked = _load_shipped_shell()
    assert checked, "no shipped shell inspected — the check is vacuous"
    offenders = []
    for rel, body in checked:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for rx, why in patterns:
                if rx.search(line):
                    offenders.append(f"{rel}: {why}: {stripped}")
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
