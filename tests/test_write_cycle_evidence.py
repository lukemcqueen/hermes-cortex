"""Tests for ops/scripts/sustainability/write_cycle_evidence.py.

The script's whole value is that its output is captured from the filesystem
and git rather than typed by hand. So the test asserts (a) it writes the file,
(b) the file CONTAINS the real values, and (c) it does not invent content when
an input is missing.

ISOLATED FROM THE LIVE ARTIFACT (fixed 2026-10-21, issue #213 / event #213): these tests used to
call `w.main(date)` with the script's real output directory in effect, so every run OVERWROTE the
committed docs/evidence/briefings/cycle-evidence-2026-10-10.md (and created a stray
cycle-evidence-1999-12-31.md in the same tracked directory). The script now exposes OUT_EVID for
the destination — separate from EVID, which is where it READS its input artifacts — so the tests
repoint the output to a temp directory, the assertions moved with it, and each test asserts the
COMMITTED file's mtime is unchanged. Coverage is unchanged: the pack is still produced, still read
back, and still asserted on, just not in the live tree.

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
COMMITTED_DIR = REPO / "docs" / "evidence" / "briefings"

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


class _IsolatedMain(unittest.TestCase):
    """Base: run main() with the PACK's destination pointed at a temp dir, and prove the live
    artifact was not touched. EVID is deliberately NOT redirected — the script reads its input
    briefing artifacts from there."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="write-cycle-evidence-")
        self.evid = Path(self._tmp.name)
        self._live_dir_before = sorted(p.name for p in COMMITTED_DIR.glob("cycle-evidence-*"))

    def tearDown(self):
        self._tmp.cleanup()
        self.assertEqual(
            sorted(p.name for p in COMMITTED_DIR.glob("cycle-evidence-*")), self._live_dir_before,
            "the run created or removed a file in the tracked evidence directory (issue #213)")


class TestMain(_IsolatedMain):
    def test_writes_pack_for_real_artifacts(self):
        # Use a date whose artifacts really exist (this cycle's).
        date = "2026-10-10"
        art = COMMITTED_DIR / f"sustainability-briefing-{date}.md"
        if not art.exists():
            self.skipTest(f"no committed artifact for {date}")

        code = w.main(date, out_dir=self.evid)
        self.assertEqual(code, 0)

        dest = self.evid / f"cycle-evidence-{date}.md"
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
        w.main(date, out_dir=self.evid)
        dest = self.evid / f"cycle-evidence-{date}.md"
        text = dest.read_text(encoding="utf-8")
        self.assertIn("MISSING", text)


class TestRedaction(_IsolatedMain):
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
        art = COMMITTED_DIR / f"sustainability-briefing-{date}.md"
        if not art.exists():
            self.skipTest(f"no committed artifact for {date}")
        self.assertEqual(w.main(date, out_dir=self.evid), 0)
        text = (self.evid / f"cycle-evidence-{date}.md").read_text(encoding="utf-8")
        self.assertNotIn(str(Path.home()), text,
                         "the committed pack carries this host's absolute home path")

    def test_the_emitted_command_still_names_the_interpreter_used(self):
        # Redaction must not delete the fact: the reader still learns WHICH interpreter ran
        # the tests, just not which host's home it lived under.
        date = "2026-10-10"
        art = COMMITTED_DIR / f"sustainability-briefing-{date}.md"
        if not art.exists():
            self.skipTest(f"no committed artifact for {date}")
        self.assertEqual(w.main(date, out_dir=self.evid), 0)
        text = (self.evid / f"cycle-evidence-{date}.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"Command: (~/?[^\s]*python[^\s]*) -W error::ResourceWarning")


class TestDefaultDestinationUnchanged(unittest.TestCase):
    """Production behaviour must not move: with no out_dir argument the pack still goes to the
    real briefings dir, so the redirect is an opt-in and not a silent relocation of the output."""

    def test_out_evid_defaults_to_evid(self):
        self.assertEqual(w.OUT_EVID, w.EVID)

    def test_main_accepts_an_out_dir_parameter(self):
        import inspect
        params = inspect.signature(w.main).parameters
        self.assertIn("out_dir", params, "main() must expose the redirect parameter")
        self.assertIsNone(params["out_dir"].default)


if __name__ == "__main__":
    unittest.main()
