import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_WATCHDOG = _REPO / "ops" / "scripts" / "health" / "agent-cron-quality-watchdog.py"
sys.path.insert(0, str(_REPO / "ops" / "scripts"))  # hermes_tz resolution

_spec = importlib.util.spec_from_file_location("agent_cron_quality_watchdog", _WATCHDOG)
watchdog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watchdog)


def test_silent_noop_accepts_angle_bracket_variant():
    """A cron agent can wrap the no-op in ASCII angle brackets (<SILENT>) after a provider
    fallback; the matcher must treat it as the healthy no-op, not flag it as token garbage.
    Scope is the cortex watchdog's own token set ([SILENT]/SILENT, uppercase)."""
    for token in ("<SILENT>", "  <SILENT>  ", "< [SILENT] >"):
        assert watchdog._is_silent_noop(token), token


def test_silent_noop_keeps_existing_forms():
    for token in ("[SILENT]", "SILENT", '["SILENT"]', "  [SILENT]  "):
        assert watchdog._is_silent_noop(token), token


def test_silent_noop_still_rejects_prose_and_unclosed_token():
    """Square brackets must stay structural; prose, a stray unclosed token, and marker
    forms outside the cortex watchdog's token set are not silence."""
    for token in ("[SILENT", "SILENT]", "the lane said SILENT mid-sentence", "no changes found",
                  "<silent>", "NO_REPLY", "<NO_REPLY>"):
        assert not watchdog._is_silent_noop(token), token