#!/usr/bin/env python3
"""Tests for fact-retention-eval.py — compaction "never silent truncation" (O7-S2).

Run: python3 tests/test_fact_retention.py
     (or: python3 -m pytest tests/test_fact_retention.py -v)

Verifies:
  1. The probe builds a compressible conversation (middle region exists)
  2. Real ContextCompressor.compress() shrinks the transcript
  3. HEAD facts survive verbatim (protect_first_n guarantee)
  4. TAIL facts survive verbatim (protect_last_n token-budget guarantee)
  5. Last actionable USER turns survive verbatim (min_tail_user_messages)
  6. A compaction summary marker is inserted (never silent deletion)
  7. Probe exits 0 with parseable JSON when all guarantees hold

The probe runs the REAL compressor mechanics (boundary math, token budgets,
tail protection) with the summarizer LLM stubbed — deterministic, no API.
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_PROBE = _REPO / "ops" / "scripts" / "manage" / "fact-retention-eval.py"
_VENV_PY = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"

_spec = importlib.util.spec_from_file_location("fre", str(_PROBE))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def test_conversation_has_all_regions():
    msgs = _mod.build_conversation()
    # system + head + middle + tail + user turns
    assert msgs[0]["role"] == "system"
    assert len(msgs) > 40, f"conversation too small: {len(msgs)}"
    texts = "\n".join(str(m.get("content") or "") for m in msgs)
    for f in _mod.HEAD_FACTS + _mod.MIDDLE_FACTS + _mod.TAIL_FACTS + _mod.USER_FACTS:
        assert f in texts, f"fact not planted: {f}"


@pytest.fixture(scope="module")
def probe_report() -> dict:
    """Run the probe ONCE, in a child process, and hand its JSON to the assertions.

    WHY A CHILD PROCESS: importing Hermes core's compressor IN-PROCESS (what these
    tests used to do) sends the import chain through the Hermes launcher, which
    re-execs the interpreter with pytest's own argv — the child then cannot import
    pytest, and the ENTIRE pytest run dies mid-suite with no failure report
    (observed: the suite stopped at 37% with rc=1 and nothing else). The probe is
    the real path regardless: it drives the same compressor mechanics with the
    summarizer stubbed and prints every guarantee, so each one is still asserted
    individually here.
    """
    if not _VENV_PY.exists():
        pytest.skip("hermes-agent venv not present on this host")
    r = subprocess.run([str(_VENV_PY), str(_PROBE)],
                       capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, f"probe rc={r.returncode}: {r.stdout[-500:]} {r.stderr[-500:]}"
    report = None
    for line in reversed(r.stdout.strip().splitlines()):
        if line.strip().startswith("{"):
            report = json.loads(line)
            break
    assert report is not None, f"no JSON in probe stdout: {r.stdout[-300:]}"
    return report


def test_compress_window_opens_and_shrinks_the_transcript(probe_report):
    """A real compress window opens (legacy tail_mode) and the transcript shrinks."""
    m = re.search(r"compressed (\d+) msgs \u2192 (\d+) msgs", probe_report["detail"])
    assert m, f"unparseable probe detail: {probe_report['detail']}"
    before, after = int(m.group(1)), int(m.group(2))
    assert after < before, f"compression did not shrink: {before} -> {after}"


def test_head_tail_and_user_facts_survive_verbatim(probe_report):
    """The hard guarantee: protected regions are never silently truncated."""
    guarantees = probe_report["guarantees"]
    for key in ("head_verbatim", "tail_verbatim", "user_turn_verbatim"):
        assert guarantees[key] is True, f"guarantee {key} failed: {probe_report}"
    retention = probe_report["retention"]
    for region in ("head", "tail", "user"):
        kept, total = retention[region].split("/")
        assert kept == total, f"{region} facts lost: {retention}"


def test_summary_marker_is_inserted(probe_report):
    """Compaction inserts a visible summary row — never silent deletion."""
    assert probe_report["guarantees"]["summary_marker_present"] is True, probe_report
    assert probe_report["summary_prefix"].startswith("[CONTEXT COMPACTION"), probe_report


def test_probe_passes_all_guarantees(probe_report):
    """The probe's own verdict, from its own process (rc=0 is asserted in the fixture)."""
    assert probe_report["passed"] is True, probe_report


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
