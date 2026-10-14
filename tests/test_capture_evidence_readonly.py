#!/usr/bin/env python3
"""The evidence capture must be read-only, sanitised, and free of reviewer directives.

Three properties, each measured on a real run or on the committed artifact rather than
asserted in prose:

  1. READ-ONLY. The capture runs `check-skill-drift-parity.py`. Without `--check` that
     tool REGENERATES `docs/evidence/skill-drift-parity.txt` (a tracked file), so an
     evidence run mutated the very artifact it was measuring - a capture that repairs
     what it measures can hide the defect it exists to show.
  2. SANITISED. The transcript is committed to a PUBLIC repo, so host identity must not
     travel with it: home paths become `$HOME`, the host line becomes `Host: <host>`,
     and `ls -l` ownership becomes `<user> <user>`. Redaction happens in the GENERATOR
     (one place, applied to every emitted line), never by hand-editing the committed
     copy - a hand-patched transcript soon disagrees with the command above it.
  3. NO DIRECTIVES. An artifact must not tell the reviewer what to conclude. The first
     committed version carried a `READ THIS FIRST` block that asserted the doctor's
     verdict ("note 0 fail ... both green") while the run it described exited 1.

Run: python3 -m pytest tests/test_capture_evidence_readonly.py -q
"""

import importlib.util
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CAPTURE = _REPO / "ops" / "scripts" / "manage" / "capture-crons-receipt-evidence.py"
_ARTIFACT = _REPO / "docs" / "evidence" / "fix-receipt-paused-crons-2026-10-14.txt"


def _capture_module():
    spec = importlib.util.spec_from_file_location("capture_evidence_under_test", _CAPTURE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_capture_asks_the_parity_tool_for_its_read_only_mode():
    src = _CAPTURE.read_text()
    hits = [l for l in src.splitlines() if "check-skill-drift-parity.py" in l]
    assert hits, "the capture must run the parity tool at all"
    assert any('"--check"' in l for l in hits), (
        "the capture must run check-skill-drift-parity.py --check; without it the run "
        "rewrites the tracked artifact it is measuring"
    )
    print("  the capture uses the parity tool's --check mode (no tracked-file write) OK")


def test_a_parity_run_without_check_would_write_but_check_does_not(tmp_path):
    """Drive the tool itself, both ways, in a temp dir - so the read-only claim is
    measured rather than read off the flag's help text."""
    tool = _REPO / "ops" / "scripts" / "manage" / "check-skill-drift-parity.py"
    spec = importlib.util.spec_from_file_location("parity_under_test", tool)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    artifact = tmp_path / "parity.txt"
    real_artifact, real_build = mod.ARTIFACT, mod.build
    try:
        mod.ARTIFACT = artifact
        mod.build = lambda: ("derived text\n", True)
        sys.argv = ["check-skill-drift-parity.py", "--check"]
        rc = mod.main()
        assert rc == 1, f"a MISSING artifact must not report success, got rc={rc}"
        assert not artifact.exists(), "--check must never write the artifact"
        sys.argv = ["check-skill-drift-parity.py"]
        mod.main()
        assert artifact.read_text() == "derived text\n", "the writing mode must still write"
    finally:
        mod.ARTIFACT, mod.build = real_artifact, real_build
        sys.argv = ["pytest"]
    print("  --check refuses a missing artifact without writing; the write mode still writes OK")


def test_the_normaliser_redacts_host_identity():
    m = _capture_module()
    assert hasattr(m, "normalise_line"), "the generator must own one redaction function"
    sample = (
        "Host: somehost\n"
        "=== [x] $ python3 /home/someuser/hermes-cortex/ops/scripts/manage/cortex-doctor.py\n"
        "-rw-r--r-- 1 someuser someuser 4096 Oct 14 10:00 jobs.json\n"
        "mycortex_reader_someuser  (a ROLE name, not identity - must survive)\n"
    )
    got = m.normalise_line(sample, home=Path("/home/someuser"),
                           user="someuser", host="somehost")
    assert "/home/someuser" not in got, got
    assert "$HOME/hermes-cortex" in got, got
    assert "Host: <host>" in got, got
    assert "someuser someuser" not in got, got
    assert "<user> <user>" in got, got
    assert "mycortex_reader_someuser" in got, "a DB role name is not identity and must survive"
    print("  home path, host line and ownership are redacted; a role name survives OK")


def test_the_normaliser_leaves_ordinary_content_alone():
    m = _capture_module()
    line = "Paused crons: reason: PASS - all 4 paused cron(s) carry a recorded reason"
    assert m.normalise_line(line, home=Path("/home/someuser"),
                            user="someuser", host="somehost") == line
    print("  ordinary output is byte-identical after normalisation OK")


def test_the_committed_artifact_carries_no_host_identity():
    text = _ARTIFACT.read_text()
    leaked = re.findall(r"/home/[A-Za-z0-9_.-]+", text)
    assert not leaked, f"absolute home paths in a public artifact: {sorted(set(leaked))[:3]}"
    # A redacted host line is the GOAL, so the assertion must forbid an UNREDACTED one
    # rather than any `Host:` line at all (the first version of this probe forbade the
    # redacted form too - it could never pass on correct output).
    unredacted = re.findall(r"(?m)^Host: (?!<host>)\S+$", text)
    assert not unredacted, f"the host line must be redacted to <host>, got {unredacted}"
    assert re.search(r"(?m)^Host: <host>$", text), "the host line must still be present"
    print("  the committed artifact carries no absolute home path and no host name OK")


def test_the_committed_artifact_does_not_tell_the_reviewer_what_to_conclude():
    text = _ARTIFACT.read_text()
    assert "READ THIS FIRST" not in text, (
        "a directive aimed at the reviewer is injection; the artifact states provenance "
        "and lets the reviewer read the output"
    )
    assert not re.search(r"(?i)note \d+ fail", text), "the artifact must not assert the verdict"
    print("  no reviewer-directed directive in the artifact OK")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
