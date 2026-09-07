#!/usr/bin/env python3
"""Tests for the bus test-traffic discipline guard in lib/cortex_bus.py.

Guards the fleet against a recurring failure mode (2026-09-07): an agent
diagnosing the bus sends a junk subject (TEST) to a peer inbox; the
receiver's handler does not recognize it, notifies Telegram ("Unknown
subject"), and the operator sees alert noise. The fix: bus_send() rejects
junk subjects before they reach the wire, and the sanctioned diagnostic
subjects (PING/DOCTOR_TEST/STATUS_REQUEST/HEARTBEAT) are the only allowed
probe traffic.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ops", "scripts"))
from lib import cortex_bus  # noqa: E402


class SubjectGuardTest(unittest.TestCase):
    def test_junk_subject_detected(self):
        for junk in ("TEST", "test", "Testing", "T1", "HELLO", "hello", "FOO", "bar", "asdf", "PLACEHOLDER"):
            self.assertTrue(cortex_bus._subject_is_junk(junk), f"expected junk: {junk}")

    def test_real_subjects_not_junk(self):
        for real in ("PING", "DOCTOR_TEST", "STATUS_REQUEST", "HEARTBEAT",
                     "EXEC", "UPDATE_REQUEST", "UPDATE_RESULT", "PROPOSAL",
                     "Skill Report: 3 custom skills"):
            self.assertFalse(cortex_bus._subject_is_junk(real), f"not junk: {real}")

    def test_diagnostic_subjects_recognized(self):
        for diag in ("PING", "DOCTOR_TEST", "STATUS_REQUEST", "HEARTBEAT"):
            self.assertTrue(cortex_bus._subject_is_diagnostic(diag))

    def test_real_subjects_not_diagnostic(self):
        for real in ("EXEC", "UPDATE_REQUEST", "PROPOSAL", "TEST"):
            self.assertFalse(cortex_bus._subject_is_diagnostic(real))

    def test_bus_send_rejects_junk_with_instruction(self):
        """The guard must reject junk subjects BEFORE the wire with a
        message teaching the caller what to use instead."""
        with self.assertRaises(ValueError) as ctx:
            cortex_bus.bus_send("inbox_moses", {"from": "esther", "subject": "TEST", "body": {"topic": "t"}})
        msg = str(ctx.exception)
        self.assertIn("junk placeholder", msg)
        self.assertIn("PING", msg)  # teaches the sanctioned alternative


if __name__ == "__main__":
    unittest.main()
