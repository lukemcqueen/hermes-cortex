"""Tests for ops/scripts/sustainability/write_cycle_evidence.py.

The script's whole value is that its output is captured from the filesystem
and git rather than typed by hand. So the test asserts (a) it writes the file,
(b) the file CONTAINS the real values, and (c) it does not invent content when
an input is missing.

stdlib-only (unittest), matching the sibling suites.

Run: python3 tests/test_write_cycle_evidence.py
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "sustainability" / "write_cycle_evidence.py"

_spec = importlib.util.spec_from_file_location("write_cycle_evidence", SCRIPT)
w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w)  # pylint: disable=protected-access


class TestHelpers(unittest.TestCase):
    def test_sha256_matches_hashlib(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.bin"
            p.write_bytes(b"abc")
            self.assertEqual(w.sha256(p), hashlib.sha256(b"abc").hexdigest())

    def test_sh_captures_stdout(self):
        out = w.sh("echo", "hello-evidence")
        self.assertIn("hello-evidence", out)

    def test_sh_does_not_raise_on_bad_command(self):
        out = w.sh("git", "not-a-real-subcommand-xyz")
        self.assertIsInstance(out, str)  # captured, surfaced, never raised


class TestMain(unittest.TestCase):
    def test_writes_pack_for_real_artifacts(self):
        # Use a date whose artifacts really exist (this cycle's).
        date = "2026-10-10"
        art = REPO / "docs" / "evidence" / "briefings" / (
            f"sustainability-briefing-{date}.md")
        if not art.exists():
            self.skipTest(f"no committed artifact for {date}")

        code = w.main(date)
        self.assertEqual(code, 0)

        dest = REPO / "docs" / "evidence" / "briefings" / (
            f"cycle-evidence-{date}.md")
        self.assertTrue(dest.exists())
        text = dest.read_text(encoding="utf-8")

        # The pack must carry the real checker verdict and real hashes,
        # not placeholders.
        self.assertIn("RESULT: ALL PASS", text)
        self.assertIn("## 5. Actual sha256", text)
        self.assertRegex(text, r"[0-9a-f]{64}\s+docs/evidence/briefings/")
        # And the sections the reviewer needs.
        for section in ("## 1. Commits", "## 2. The actual diffs",
                        "## 3. Canonical checker output",
                        "## 4. Test output",
                        "## 6. DOCX/PDF content extraction"):
            self.assertIn(section, text)

    def test_reports_missing_artifact_as_missing(self):
        date = "1999-12-31"
        w.main(date)
        dest = REPO / "docs" / "evidence" / "briefings" / (
            f"cycle-evidence-{date}.md")
        try:
            text = dest.read_text(encoding="utf-8")
            self.assertIn("MISSING", text)
        finally:
            dest.unlink(missing_ok=True)  # never leave junk for a fake date


class TestRedaction(unittest.TestCase):
    """The pack is COMMITTED to a public repo: an absolute home path in it is both noise the
    secret-leak detector flags on every refresh and a command the next reader cannot re-run.
    Redaction happens at the GENERATOR, so the committed copy always agrees with the command
    printed above it — a hand-patched copy drifts from the output it claims to show."""

    def test_redact_replaces_the_home_prefix(self):
        home = str(Path.home())
        self.assertEqual(w._redact(f"{home}/.hermes/cron/output/.venv/bin/python"), "~/.hermes/cron/output/.venv/bin/python")

    def test_redact_leaves_other_text_untouched(self):
        for text in ("plain output", "a relative/path.py", "/usr/bin/python3", ""):
            self.assertEqual(w._redact(text), text)

    def test_redact_keeps_a_bare_agent_name(self):
        # Narrow by design: only the HOME PREFIX is rewritten. A host name that is also a
        # legitimate identifier elsewhere must survive, or redaction mangles real content.
        self.assertIn("esther", w._redact("agent esther reported this"))

    def test_the_written_pack_carries_no_absolute_home_path(self):
        date = "2026-10-10"
        art = REPO / "docs" / "evidence" / "briefings" / f"sustainability-briefing-{date}.md"
        if not art.exists():
            self.skipTest(f"no committed artifact for {date}")
        self.assertEqual(w.main(date), 0)
        text = (REPO / "docs" / "evidence" / "briefings" /
                f"cycle-evidence-{date}.md").read_text(encoding="utf-8")
        self.assertNotIn(str(Path.home()), text,
                         "the committed pack carries this host's absolute home path")

    def test_the_emitted_command_still_names_the_interpreter_used(self):
        # Redaction must not delete the fact: the reader still learns WHICH interpreter ran
        # the tests, just not which host's home it lived under.
        date = "2026-10-10"
        art = REPO / "docs" / "evidence" / "briefings" / f"sustainability-briefing-{date}.md"
        if not art.exists():
            self.skipTest(f"no committed artifact for {date}")
        self.assertEqual(w.main(date), 0)
        text = (REPO / "docs" / "evidence" / "briefings" /
                f"cycle-evidence-{date}.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"Command: (~/?[^\s]*python[^\s]*) -W error::ResourceWarning")


if __name__ == "__main__":
    unittest.main()
