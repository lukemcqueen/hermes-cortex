#!/usr/bin/env python3
"""Verify the committed landing evidence for `land-nonhermes-lock-fix`.

Hermetic: parses the committed artifacts under docs/evidence/ only — no git, no
network, no services. Re-runnable by any reviewer at HEAD:

    python3 -B tests/test_land_nonhermes_lock_fix_evidence.py

Exits non-zero if any assertion fails.
"""
import re
import unittest
from pathlib import Path

EV = Path(__file__).resolve().parents[1] / "docs" / "evidence"
DOGFOOD = EV / "land-nonhermes-lock-fix-dogfood-2026-10-10.txt"
DOCTOR = EV / "land-nonhermes-lock-fix-doctor-2026-10-10.txt"
SUMMARY = EV / "land-nonhermes-lock-fix-summary-2026-10-10.md"

OVERALL_RE = re.compile(
    r"Overall:\s+WARNING\s+\((\d+) pass · (\d+) warn · (\d+) fail · (\d+) info\)"
)
DEPLOY_SYNC_LINE = "Deploy sync — deployed commit matches HEAD"
DOGFOOD_PASS_LINE = "DOGFOOD PASSED — deployed state verified clean."

# Every warning source the doctor reported in the committed transcript.
WARNING_SOURCES = (
    "Repo clean",
    "AGENTS.md efficiency",
    "Stale deploy",
    "cortex-deployment-sync",
    "cron-job-management",
    "fleet-commands",
    "governance-closeout",
    "governance-lock-lifecycle",
    "mycortex",
    "psql-automation",
    "change-checklist",
)


def parse_overall(text):
    """Return the doctor's overall counts, or None when the line is absent."""
    match = OVERALL_RE.search(text)
    if match is None:
        return None
    return dict(zip(("pass", "warn", "fail", "info"), (int(g) for g in match.groups())))


def doctor_is_clean(text):
    """True only when the doctor summary line is present and reports zero failures."""
    counts = parse_overall(text)
    return counts is not None and counts["fail"] == 0


class LandingEvidence(unittest.TestCase):
    def test_artifacts_are_committed(self):
        for path in (DOGFOOD, DOCTOR, SUMMARY):
            self.assertTrue(path.is_file(), f"missing artifact: {path}")

    def test_dogfood_transcript_records_a_pass(self):
        text = DOGFOOD.read_text(encoding="utf-8")
        self.assertIn(DOGFOOD_PASS_LINE, text)
        self.assertIn("DOGFOOD_RC=0", text)

    def test_doctor_transcript_records_zero_failures_and_12_warnings(self):
        counts = parse_overall(DOCTOR.read_text(encoding="utf-8"))
        self.assertIsNotNone(counts, "doctor overall summary line not found")
        self.assertEqual(counts["fail"], 0, "doctor reported failing checks")
        self.assertEqual(counts["warn"], 12, "unexpected doctor warning count")

    def test_doctor_transcript_records_deploy_sync_pass(self):
        self.assertIn(DEPLOY_SYNC_LINE, DOCTOR.read_text(encoding="utf-8"))

    def test_doctor_exit_code_is_recorded(self):
        self.assertIn("DOCTOR_RC=1", DOCTOR.read_text(encoding="utf-8"))

    def test_summary_disposes_of_every_warning_source(self):
        text = SUMMARY.read_text(encoding="utf-8")
        for source in WARNING_SOURCES:
            self.assertIn(source, text, f"summary does not dispose of {source!r}")

    def test_detector_rejects_a_failing_doctor_run(self):
        """The detector must discriminate: a run with failures is NOT clean."""
        real = DOCTOR.read_text(encoding="utf-8")
        counts = parse_overall(real)
        clean_line = f"{counts['pass']} pass · {counts['warn']} warn · {counts['fail']} fail"
        broken = real.replace(
            clean_line, f"{counts['pass']} pass · {counts['warn']} warn · 1 fail"
        )
        self.assertNotEqual(broken, real, "fixture did not modify the summary line")
        self.assertFalse(doctor_is_clean(broken))
        self.assertEqual(parse_overall(broken)["fail"], 1)

    def test_detector_accepts_a_clean_doctor_run(self):
        self.assertTrue(doctor_is_clean(DOCTOR.read_text(encoding="utf-8")))

    def test_detector_reports_absent_summary_as_not_clean(self):
        self.assertFalse(doctor_is_clean("no summary line here"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
