#!/usr/bin/env python3
"""Tests for check-latest-briefing.py — the delivered-briefing gate.

Hermetic: every case builds its own temp fixtures (jobs.json, briefing dir,
stub canonical checker) and drives the shipped script AS A PROCESS. No live
cron, no live briefing and no live state appears in an assertion.

Runs under pytest AND standalone:
    python3 tests/test_check_latest_briefing.py
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "check-latest-briefing.py"
BRIEF_JOB = "local-daily-sustainability-briefing"


def _run(args, **kw):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=120, **kw)


def _jobs_json(path: Path, name: str = BRIEF_JOB, enabled: bool = True) -> Path:
    path.write_text(json.dumps(
        {"jobs": [{"id": "deadbeef", "name": name, "enabled": enabled}]}))
    return path


def _briefing(out_dir: Path, date: str, body: str = "text") -> Path:
    p = out_dir / f"sustainability-briefing-{date}.md"
    p.write_text(body)
    return p


def _stub_checker(path: Path, rc: int, line: str) -> Path:
    """A canonical-checker stand-in: module exposing main(date, dir) -> int.

    The gate loads the checker as a MODULE (not a subprocess), so the double
    must mirror that interface, register its output, and return the code —
    a stub that printed at import time would leak past the gate's capture.
    """
    path.write_text("def main(date, directory):\n"
                    f"    print({line!r})\n"
                    f"    return {rc}\n")
    return path


def _minimal_docx(path: Path, text: str = "EmpCo Amy 2026") -> None:
    """A real .docx: a zip carrying word/document.xml (canonical checker reads it)."""
    import zipfile
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml",
                   f"<w:document><w:t>{text}</w:t></w:document>")


# ---------------------------------------------------------------- test cases

def test_not_applicable_is_silent_when_no_briefing_cron():
    """A host that does not run the briefing cron must not be flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "out").mkdir()
        jobs = _jobs_json(tmp / "jobs.json", name="some-other-job")
        r = _run(["--dir", str(tmp / "out"), "--jobs", str(jobs)])
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        assert r.stdout == "", f"not-applicable must be silent, got: {r.stdout!r}"


def test_pass_is_silent():
    """A delivered briefing that satisfies the checker produces no output."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        _briefing(out, "2026-10-21")
        jobs = _jobs_json(tmp / "jobs.json")
        checker = _stub_checker(tmp / "stub.py", 0, "RESULT: ALL PASS")
        r = _run(["--dir", str(out), "--jobs", str(jobs),
                  "--checker", str(checker), "--today", "2026-10-21"])
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        assert r.stdout == "", f"PASS must be silent, got: {r.stdout!r}"


def test_fail_is_reported_with_the_checkers_own_output():
    """A failing delivered briefing exits 1 and names the failing check."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        _briefing(out, "2026-10-21")
        jobs = _jobs_json(tmp / "jobs.json")
        checker = _stub_checker(tmp / "stub.py", 1,
                                "[words] count=1299 (600-1200) FAIL")
        r = _run(["--dir", str(out), "--jobs", str(jobs),
                  "--checker", str(checker), "--today", "2026-10-21"])
        assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
        assert "2026-10-21" in r.stdout, r.stdout
        assert "[words]" in r.stdout, f"checker output not carried: {r.stdout!r}"


def test_stale_delivery_is_reported():
    """An enabled cron with no recent artifact is a failure, not a silence."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        _briefing(out, "2026-10-01")
        jobs = _jobs_json(tmp / "jobs.json")
        checker = _stub_checker(tmp / "stub.py", 0, "RESULT: ALL PASS")
        r = _run(["--dir", str(out), "--jobs", str(jobs),
                  "--checker", str(checker), "--today", "2026-10-21"])
        assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
        assert "STALE" in r.stdout, r.stdout


def test_no_artifacts_with_enabled_cron_is_could_not_verify():
    """rc 3 is its own outcome: cannot check is never reported as a pass."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        jobs = _jobs_json(tmp / "jobs.json")
        checker = _stub_checker(tmp / "stub.py", 0, "RESULT: ALL PASS")
        r = _run(["--dir", str(out), "--jobs", str(jobs),
                  "--checker", str(checker), "--today", "2026-10-21"])
        assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
        assert "COULD NOT VERIFY" in r.stdout, r.stdout


def test_missing_checker_is_could_not_verify():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        _briefing(out, "2026-10-21")
        jobs = _jobs_json(tmp / "jobs.json")
        r = _run(["--dir", str(out), "--jobs", str(jobs),
                  "--checker", str(tmp / "absent.py"), "--today", "2026-10-21"])
        assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
        assert "COULD NOT VERIFY" in r.stdout, r.stdout


def test_real_canonical_checker_reports_a_contract_violation():
    """No --checker: the script must import the sibling canonical checker and
    surface ITS verdict. The artifact violates the word budget (1300 words)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        body = ["## 1. Headline", "## 2. Materials", "## 3. Policy",
                "## 4. Market", "## For Your Radar"]
        body += [f"Source: https://example.com/item-{i}" for i in range(13)]
        body += ["word"] * 1300
        _briefing(out, "2026-10-21", "\n".join(body))
        _minimal_docx(out / "sustainability-briefing-2026-10-21.docx")
        (out / "sustainability-briefing-2026-10-21.pdf").write_bytes(b"x" * 2000)
        jobs = _jobs_json(tmp / "jobs.json")
        r = _run(["--dir", str(out), "--jobs", str(jobs),
                  "--today", "2026-10-21", "--date", "2026-10-21"])
        assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
        assert "[words]" in r.stdout, f"canonical checker not driven: {r.stdout!r}"


def test_explicit_date_ignores_applicability():
    """--date is an explicit request to check one artifact."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        _briefing(out, "2026-10-21")
        jobs = _jobs_json(tmp / "jobs.json", name="some-other-job")
        checker = _stub_checker(tmp / "stub.py", 1, "RESULT: FAILURES PRESENT")
        r = _run(["--dir", str(out), "--jobs", str(jobs),
                  "--checker", str(checker), "--date", "2026-10-21"])
        assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)


def test_explicit_date_with_no_artifact_is_could_not_verify():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        jobs = _jobs_json(tmp / "jobs.json")
        r = _run(["--dir", str(out), "--jobs", str(jobs), "--date", "2026-10-21"])
        assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)


def test_malformed_today_is_could_not_verify():
    """A bad --today is reported, not raised (boundary input)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        _briefing(out, "2026-10-21")
        jobs = _jobs_json(tmp / "jobs.json")
        r = _run(["--dir", str(out), "--jobs", str(jobs), "--today", "bogus"])
        assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
        assert "COULD NOT VERIFY" in r.stdout, r.stdout
        assert "Traceback" not in r.stderr, r.stderr


def test_checker_that_raises_is_could_not_verify_not_a_traceback():
    """A checker that cannot run its parser is reported, never crashed on."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "out"
        out.mkdir()
        _briefing(out, "2026-10-21")
        jobs = _jobs_json(tmp / "jobs.json")
        bad = tmp / "bad.py"
        bad.write_text("def main(date, directory):\n"
                       "    raise ValueError('corrupt artifact')\n")
        r = _run(["--dir", str(out), "--jobs", str(jobs), "--checker", str(bad),
                  "--date", "2026-10-21"])
        assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
        assert "COULD NOT VERIFY" in r.stdout, r.stdout
        assert "Traceback" not in r.stderr, r.stderr


# --------------------------------------------------------------- standalone

def _tests():
    return [v for k, v in sorted(globals().items())
            if k.startswith("test_") and callable(v)]


def main() -> int:
    failed = []
    for fn in _tests():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — report, do not swallow
            failed.append(fn.__name__)
            print(f"FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {fn.__name__}")
    total = len(_tests())
    print(f"{total - len(failed)}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
