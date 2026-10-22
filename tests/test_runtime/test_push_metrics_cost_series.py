"""agent-push-metrics.sh — the per-cron cost series, and its fail-soft rule.

Story c579ef95 [cost/3]: the sink at :14005 must carry cost, not only node metrics.
The client is UNIVERSAL (288 runs/day on every host), so the one thing that must
never happen is a cost-metrics failure turning a healthy push into a failed run —
or, worse, a missing generator being reported as $0 spend.

These tests run the REAL client with a stub curl (PUSH_METRICS_CURL) that records
the payload it receives, and point PUSH_METRICS_COST_BIN at three generators:
absent, working, and failing.
"""

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "scripts" / "manage" / "agent-push-metrics.sh"

SINK_URL = "http://127.0.0.1:19999/api/v1/import/prometheus"


def _stub_curl(tmp: Path, capture: Path, code: str = "204") -> Path:
    p = tmp / "stub-curl"
    p.write_text(
        "#!/usr/bin/env bash\n"
        'cat > "$PUSH_METRICS_TEST_CAPTURE"\n'
        f"printf '%s' '{code}'\n"
    )
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _generator(tmp: Path, *, lines=(), rc=0, name="cost-gen", stderr="") -> Path:
    p = tmp / name
    body = "#!/usr/bin/env python3\n"
    if lines:
        body += "print(" + repr("\n".join(lines)) + ")\n"
    if stderr:
        body += "import sys; print(" + repr(stderr) + ", file=sys.stderr)\n"
    body += f"raise SystemExit({rc})\n"
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _run(tmp: Path, capture: Path, cost_bin: Path):
    home = tmp / "home"
    (home / ".hermes-cortex").mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "AGENT_NAME": "test-agent",
        "VICTORIA_METRICS_URL": SINK_URL,
        "PUSH_METRICS_CURL": str(_stub_curl(tmp, capture)),
        "PUSH_METRICS_TEST_CAPTURE": str(capture),
        "PUSH_METRICS_STATE_FILE": str(tmp / "state" / "push-metrics.state"),
        "PUSH_METRICS_COST_BIN": str(cost_bin),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=180
    )


def test_absent_generator_pushes_normally_and_claims_nothing(tmp_path):
    capture = tmp_path / "payload.txt"
    r = _run(tmp_path, capture, tmp_path / "no-such-generator.py")
    assert r.returncode == 0, r.stderr
    payload = capture.read_text()
    assert "node_uptime_seconds{" in payload, "the node payload must still be pushed"
    assert "hermes_cron_" not in payload
    assert "cost" not in r.stderr.lower(), "an absent optional generator is not an error to report"


def test_working_generator_lands_in_the_same_push(tmp_path):
    capture = tmp_path / "payload.txt"
    gen = _generator(
        tmp_path,
        lines=[
            'hermes_cron_tokens_total{agent="test-agent",job_id="jobA"} 200',
            'hermes_cron_cost_usd{agent="test-agent",job_id="jobA"} 0.400000',
        ],
    )
    r = _run(tmp_path, capture, gen)
    assert r.returncode == 0, r.stderr
    payload = capture.read_text()
    assert 'hermes_cron_tokens_total{agent="test-agent",job_id="jobA"} 200' in payload
    assert 'hermes_cron_cost_usd{agent="test-agent",job_id="jobA"} 0.400000' in payload
    assert "node_uptime_seconds{" in payload, "cost series must be added to, not replace, the payload"


def test_failing_generator_does_not_fail_the_push_and_says_so(tmp_path):
    capture = tmp_path / "payload.txt"
    gen = _generator(tmp_path, rc=3, lines=[
        'hermes_cron_tokens_total{agent="test-agent",job_id="jobA"} 1'], stderr="why: state.db locked")
    r = _run(tmp_path, capture, gen)
    assert r.returncode == 0, "a broken optional generator must not error the cron: " + r.stderr
    assert "hermes_cron_" not in capture.read_text(), "a failed generator's series must not be sent"
    assert "cost metrics" in r.stderr and "3" in r.stderr, "the gap must be visible, not silent"
    assert "zero" in r.stderr.lower(), "the line must say a missing series is not $0 spend"
    assert "why: state.db locked" in r.stderr, (
        "the generator's own diagnostic must be forwarded, not swallowed (exit code alone "
        "sends the reader hunting for the reason)")
