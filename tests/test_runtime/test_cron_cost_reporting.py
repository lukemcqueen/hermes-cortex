"""cron-cost-metrics.py + orch-weekly-cost-report.py — per-cron cost series and the weekly report.

Why this exists (story c579ef95 [cost/3]): the fleet knows its TOKENS (per-cron
`usage_audit.jsonl`) and, since 2026-10-06, no longer stores a price table at all —
a stored price rots on every provider hike, which is why the `cron-costs.db` stack
was deleted. The durable spend truth is Hermes' own `state.db` -> `sessions`
(`estimated_cost_usd`, written live at current prices, cron rows named
`cron_<jobid>_<ts>`).

Two properties are load-bearing and are what these tests pin:

  1. a number that cannot be read is OMITTED and declared unavailable
     (`hermes_cron_cost_available 0` / a `NO DATA` coverage line) —
     never a fabricated 0, and never an alert built on no data;
  2. the weekly report alerts (rc=1) only from MEASURED data, and says which
     hosts are unmeasured instead of extrapolating.

Everything is driven through the scripts' own CLI against temp fixtures:
no live audit log, no live state.db, no real governance store. Fixture times are
relative to now, because the report windows on the clock.
"""

import http.server
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
METRICS = REPO / "ops" / "scripts" / "manage" / "cron-cost-metrics.py"
REPORT = REPO / "ops" / "scripts" / "manage" / "orch-weekly-cost-report.py"

AGENT = "test-agent"


def _audit(tmp: Path, rows) -> Path:
    p = tmp / "usage_audit.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def _sessions_db(tmp: Path, rows) -> Path:
    """Minimal stand-in for ~/.hermes/state.db's `sessions` table.

    Column names mirror the LIVE schema (verified 2026-10-22): the key is `id`
    — there is no `session_id` column. A fixture that invents one keeps a wrong
    query green, which is exactly how the first version of this generator
    shipped a read that never matched a single row.

    Only the FOUR columns the scripts actually read are declared: both scripts
    issue an explicit column list (`SELECT id, estimated_cost_usd ... WHERE
    source = 'cron'` in the generator; `SELECT started_at, estimated_cost_usd
    ... WHERE source = 'cron' AND started_at >= ?` in the report) — neither does
    `SELECT *`, so the other ~58 live columns cannot be reached by a query here.
    `input_tokens`/`output_tokens` are carried only so the shipped
    estimated_cost_usd semantics stay visible; no script reads them.
    """
    p = tmp / "state.db"
    con = sqlite3.connect(p)
    con.execute(
        "CREATE TABLE sessions (id TEXT, source TEXT, started_at REAL,"
        " input_tokens INTEGER, output_tokens INTEGER, estimated_cost_usd REAL)"
    )
    con.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return p


def _run(script: Path, *args, env_extra=None, home=None):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    if home is not None:
        # A test of the host-derived identity fallback must control HOME —
        # otherwise it reads the real host's agent.env and the "no identity"
        # branch is unreachable (a fixture that omits the field it tests).
        env["HOME"] = str(home)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(script), *args], env=env, capture_output=True, text=True, timeout=120
    )


def _value(stdout: str, metric_fragment: str) -> float:
    """Last whitespace-separated field of the first line carrying this fragment."""
    for line in stdout.splitlines():
        if metric_fragment in line and not line.startswith("#"):
            return float(line.split()[-1])
    raise AssertionError(f"no series line carrying {metric_fragment!r} in:\n{stdout}")


# ── the generator ────────────────────────────────────────────────────────────

def test_tokens_are_summed_per_job_and_fires_counted(tmp_path):
    audit = _audit(
        tmp_path,
        [
            {"job_id": "jobA", "total_tokens": 120},
            {"job_id": "jobA", "total_tokens": 80},
            {"job_id": "jobB", "total_tokens": 5},
        ],
    )
    r = _run(METRICS, "--prometheus", "--agent", AGENT, "--audit", str(audit))
    assert r.returncode == 0, r.stderr
    assert _value(r.stdout, 'hermes_cron_tokens_total{agent="test-agent",job_id="jobA"}') == 200
    assert _value(r.stdout, 'hermes_cron_fires_total{agent="test-agent",job_id="jobA"}') == 2
    assert _value(r.stdout, 'hermes_cron_tokens_total{agent="test-agent",job_id="jobB"}') == 5


def test_spend_comes_from_the_sessions_table(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    db = _sessions_db(
        tmp_path,
        [
            ("cron_jobA_t1", "cron", 1.0, 100, 10, 0.25),
            ("cron_jobA_t2", "cron", 2.0, 100, 10, 0.15),
            ("cli_t3", "cli", 3.0, 100, 10, 9.99),  # not cron — must not be counted
        ],
    )
    r = _run(METRICS, "--prometheus", "--agent", AGENT, "--audit", str(audit), "--state-db", str(db))
    assert r.returncode == 0, r.stderr
    assert _value(r.stdout, 'hermes_cron_cost_usd{agent="test-agent",job_id="jobA"}') == 0.4
    assert _value(r.stdout, 'hermes_cron_cost_usd_total{agent="test-agent"}') == 0.4
    assert _value(r.stdout, 'hermes_cron_cost_available{agent="test-agent"}') == 1


def test_unreadable_spend_is_declared_unavailable_never_zero(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    r = _run(
        METRICS,
        "--prometheus",
        "--agent",
        AGENT,
        "--audit",
        str(audit),
        "--state-db",
        str(tmp_path / "missing.db"),
    )
    assert r.returncode == 0, r.stderr
    assert _value(r.stdout, 'hermes_cron_cost_available{agent="test-agent"}') == 0
    assert "hermes_cron_cost_usd{" not in r.stdout, "an unreadable spend source must not emit a value"
    assert "unavailable" in r.stderr


def test_malformed_audit_lines_are_skipped_not_fatal(tmp_path):
    p = tmp_path / "usage_audit.jsonl"
    p.write_text('{"job_id": "jobA", "total_tokens": 7}\nnot json at all\n[1,2]\n')
    r = _run(METRICS, "--prometheus", "--agent", AGENT, "--audit", str(p))
    assert r.returncode == 0, r.stderr
    assert _value(r.stdout, 'hermes_cron_tokens_total{agent="test-agent",job_id="jobA"}') == 7


def test_no_source_at_all_is_its_own_outcome(tmp_path):
    r = _run(
        METRICS,
        "--prometheus",
        "--agent",
        AGENT,
        "--audit",
        str(tmp_path / "absent.jsonl"),
        "--state-db",
        str(tmp_path / "absent.db"),
    )
    # rc=2 is this tool's OWN documented code for "nothing readable at all"
    # (see its module docstring: 0 = series emitted, 2 = no data). It is
    # deliberately distinct from 0 so an absent source can never be mistaken for
    # a successful empty push, and the client treats it as "omit the series".
    assert r.returncode == 2, "nothing readable must not look like a successful empty push"
    assert r.stdout.strip() == ""
    assert "no readable source" in r.stderr, "and it must say what it could not read"


def test_missing_agent_name_is_refused(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 1}])
    r = _run(METRICS, "--prometheus", "--agent", "", "--audit", str(audit))
    assert r.returncode == 2
    assert "AGENT_NAME" in r.stderr, "misattributed cost metrics are worse than none"


# ── the weekly report ────────────────────────────────────────────────────────

def test_weekly_report_alerts_above_the_daily_target(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 1000}])
    now = time.time()
    # THE FORMULA UNDER TEST: spend is summed per UTC day, and the average is
    # total / number of MEASURED days (days carrying cron spend) — NOT total/7.
    # Two measured days at 12.00 and 14.00 therefore give exactly 13.00; a
    # total-divide-by-window implementation would give ~3.71 and fail here.
    db = _sessions_db(
        tmp_path,
        [
            ("cron_jobA_d1", "cron", now, 1, 1, 12.0),
            ("cron_jobA_d2", "cron", now - 86400, 1, 1, 14.0),
        ],
    )
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7")
    assert r.returncode == 1, "a breach must be a failed run, not a quiet line"
    assert "FLEET COST ABOVE TARGET" in r.stdout
    assert "13.00" in r.stdout, "the alert must carry the measured average"


def test_weekly_report_is_quiet_below_the_daily_target(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 1000}])
    db = _sessions_db(tmp_path, [("cron_jobA_d1", "cron", time.time(), 1, 1, 1.5)])
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FLEET COST ABOVE TARGET" not in r.stdout
    assert "1.50" in r.stdout


def test_weekly_report_target_is_configurable(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    db = _sessions_db(tmp_path, [("cron_jobA_d1", "cron", time.time(), 1, 1, 3.0)])
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7",
             env_extra={"CORTEX_COST_DAILY_TARGET_USD": "2"})
    assert r.returncode == 1
    assert "FLEET COST ABOVE TARGET" in r.stdout


def test_weekly_report_without_spend_data_says_no_data_and_does_not_alert(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    r = _run(
        REPORT,
        "--audit",
        str(audit),
        "--state-db",
        str(tmp_path / "missing.db"),
        "--days",
        "7",
    )
    assert r.returncode == 0, "no data is not a breach"
    assert "NO DATA" in r.stdout
    assert "FLEET COST ABOVE TARGET" not in r.stdout


def test_weekly_report_ignores_sessions_outside_the_window(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    db = _sessions_db(
        tmp_path,
        [
            ("cron_jobA_in", "cron", time.time(), 1, 1, 1.0),
            ("cron_jobA_out", "cron", time.time() - 40 * 86400, 1, 1, 999.0),
        ],
    )
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7")
    assert r.returncode == 0, r.stdout
    assert "1.00" in r.stdout and "999" not in r.stdout, "the window filter is what makes the number"


def test_weekly_report_states_what_is_not_measured(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10}])
    db = _sessions_db(tmp_path, [("cron_jobA_d1", "cron", time.time(), 1, 1, 1.0)])
    r = _run(REPORT, "--audit", str(audit), "--state-db", str(db), "--days", "7")
    assert "COVERAGE" in r.stdout
    assert "cost/4" in r.stdout, "the unmeasured worker hosts must be named, not extrapolated"


# ── [cost/4] host cost summary — the mode a worker host is asked to run ──────
#
# Slice 6b7d9b8a goes to a worker host as an `EXEC` of this same deployed
# script, so the mode that matters is the one the bus handler actually runs:
# ONE JSON object on stdout, sized for an EXEC_RESULT body, carrying a window
# filter, per-day and per-job token totals, the host's OWN identity, and a
# Langfuse probe that reports absence rather than guessing.

LANGFUSE_DAILY_OK = {
    "data": [
        {
            "date": "2026-10-23",
            "countTraces": 63,
            "countObservations": 3521,
            "totalCost": 5.13393171382,
            "usage": [
                {
                    "model": "deepseek/deepseek-v4.1-flash",
                    "inputUsage": 248233407,
                    "outputUsage": 910020,
                    "totalUsage": 249643409,
                    "totalCost": 4.02889618,
                    "countObservations": 1392,
                    "countTraces": 59,
                }
            ],
        }
    ],
    "meta": {"page": 1, "limit": 2, "totalItems": 1, "totalPages": 1},
}


class _LangfuseStub:
    """Stand-in for the live /api/public/metrics/daily endpoint.

    The body used by the test below is the LIVE response shape, read from
    http://127.0.0.1:3000/api/public/metrics/daily?limit=2 on 2026-10-24
    (keys `date`, `countTraces`, `countObservations`, `totalCost`, and a
    `usage` list). It records the request path and Authorization header so
    the test can assert the probe is authenticated and aimed at the right
    endpoint — a stub that accepts anything would not catch a wrong path.
    """

    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __enter__(self):
        payload, requests = self.payload, self.requests

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(
                    {"path": self.path, "auth": self.headers.get("Authorization")}
                )
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):  # noqa: A002 — signature matches the base class
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def _summary(r):
    """The tool must print the JSON object and nothing else — an EXEC body is
    the whole stdout, so a stray log line makes the result unparseable."""
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_json_summary_windows_by_since(tmp_path):
    audit = _audit(
        tmp_path,
        [
            {"job_id": "jobA", "total_tokens": 9999, "ts": "2026-10-05T10:00:00Z"},
            {"job_id": "jobA", "total_tokens": 100, "ts": "2026-10-06T10:00:00Z"},
            {"job_id": "jobA", "total_tokens": 20, "ts": "2026-10-24T09:00:00Z"},
        ],
    )
    d = _summary(
        _run(
            METRICS,
            "--json-summary",
            "--agent",
            AGENT,
            "--audit",
            str(audit),
            "--since",
            "2026-10-06",
            "--langfuse-url",
            "http://127.0.0.1:1",
        )
    )
    assert [row["date"] for row in d["per_day"]] == ["2026-10-06", "2026-10-24"]
    assert [row["tokens"] for row in d["per_day"]] == [100, 20]
    assert all(row["fires"] == 1 for row in d["per_day"])
    assert d["window"]["since"] == "2026-10-06"
    assert d["per_job"] == [{"job_id": "jobA", "fires": 2, "tokens": 120}], (
        "the row before --since must not reach the totals: the filter is what "
        "makes the number"
    )


def test_json_summary_counts_rows_without_a_usable_timestamp(tmp_path):
    audit = _audit(
        tmp_path,
        [
            {"job_id": "jobA", "total_tokens": 5},
            {"job_id": "jobA", "total_tokens": 7, "ts": "not-a-date"},
            {"job_id": "jobA", "total_tokens": 11, "ts": "2026-10-20T00:00:00Z"},
        ],
    )
    d = _summary(
        _run(
            METRICS,
            "--json-summary",
            "--agent",
            AGENT,
            "--audit",
            str(audit),
            "--since",
            "2026-10-06",
            "--langfuse-url",
            "http://127.0.0.1:1",
        )
    )
    assert d["audit"]["skipped_rows"] == 2
    assert d["per_job"][0]["tokens"] == 11, (
        "an unplaceable row must be declared, never silently counted into a day"
    )
    assert sum(row["tokens"] for row in d["per_day"]) == 11


def test_json_summary_per_job_is_capped_and_declares_the_remainder(tmp_path):
    rows = [
        {"job_id": f"job{i:02d}", "total_tokens": (100 - i), "ts": "2026-10-20T00:00:00Z"}
        for i in range(20)
    ]
    audit = _audit(tmp_path, rows)
    d = _summary(
        _run(
            METRICS,
            "--json-summary",
            "--agent",
            AGENT,
            "--audit",
            str(audit),
            "--langfuse-url",
            "http://127.0.0.1:1",
        )
    )
    assert len(d["per_job"]) == 15, "the cap is what keeps the body inside an EXEC_RESULT"
    assert d["per_job_omitted"] == 5, "a capped list must say how much it hid"
    tokens = [row["tokens"] for row in d["per_job"]]
    assert tokens == sorted(tokens, reverse=True)
    assert d["per_job"][0]["job_id"] == "job00"


def test_json_summary_reports_unreadable_spend_as_unavailable_never_zero(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10, "ts": "2026-10-20T00:00:00Z"}])
    r = _run(
        METRICS,
        "--json-summary",
        "--agent",
        AGENT,
        "--audit",
        str(audit),
        "--state-db",
        str(tmp_path / "missing.db"),
        "--langfuse-url",
        "http://127.0.0.1:1",
    )
    d = _summary(r)
    assert d["spend"]["available"] is False
    assert "lifetime_usd" not in d["spend"], "an unreadable source must not be reported as $0"
    assert d["spend"]["reason"]


def test_agent_identity_falls_back_to_the_host_env_file(tmp_path):
    home = tmp_path / "home"
    (home / ".hermes-cortex").mkdir(parents=True)
    (home / ".hermes-cortex" / "agent.env").write_text("AGENT_NAME=worker-nine\n")
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10, "ts": "2026-10-20T00:00:00Z"}])
    d = _summary(
        _run(
            METRICS,
            "--json-summary",
            "--audit",
            str(audit),
            "--langfuse-url",
            "http://127.0.0.1:1",
            home=home,
        )
    )
    assert d["agent"] == "worker-nine", (
        "an EXEC passes no --agent, so the label must come from the host's own "
        "agent.env or the aggregate cannot be attributed to a host"
    )


def test_agent_identity_is_refused_rather_than_guessed(tmp_path):
    home = tmp_path / "empty-home"
    home.mkdir()
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10, "ts": "2026-10-20T00:00:00Z"}])
    r = _run(
        METRICS,
        "--json-summary",
        "--audit",
        str(audit),
        "--langfuse-url",
        "http://127.0.0.1:1",
        home=home,
    )
    assert r.returncode == 2, "a host that cannot name itself must not report metrics"
    assert "AGENT_NAME" in r.stderr
    assert r.stdout.strip() == ""


def test_exactly_one_output_mode_is_required(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10, "ts": "2026-10-20T00:00:00Z"}])
    neither = _run(METRICS, "--agent", AGENT, "--audit", str(audit))
    assert neither.returncode != 0, "no mode is a usage error, not an empty success"
    both = _run(
        METRICS, "--prometheus", "--json-summary", "--agent", AGENT, "--audit", str(audit)
    )
    assert both.returncode != 0


def test_prometheus_mode_ignores_the_window(tmp_path):
    """The universal producer's payload must not change shape because a window
    option exists: `agent-push-metrics.sh` runs this every 5 minutes on every
    host and never passes --since."""
    audit = _audit(
        tmp_path,
        [
            {"job_id": "jobA", "total_tokens": 100, "ts": "2026-01-01T00:00:00Z"},
            {"job_id": "jobB", "total_tokens": 20, "ts": "2026-10-24T00:00:00Z"},
        ],
    )
    r = _run(
        METRICS, "--prometheus", "--agent", AGENT, "--audit", str(audit), "--since", "2026-10-06"
    )
    assert r.returncode == 0, r.stderr
    assert _value(r.stdout, 'hermes_cron_tokens_total{agent="test-agent",job_id="jobA"}') == 100
    assert _value(r.stdout, 'hermes_cron_fires_total{agent="test-agent",job_id="jobA"}') == 1


def test_langfuse_absence_is_recorded_not_guessed(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10, "ts": "2026-10-20T00:00:00Z"}])
    d = _summary(
        _run(
            METRICS,
            "--json-summary",
            "--agent",
            AGENT,
            "--audit",
            str(audit),
            "--langfuse-url",
            "http://127.0.0.1:1",
        )
    )
    assert d["langfuse"]["checked"] is True
    assert d["langfuse"]["present"] is False, (
        "a host with no Langfuse must say so; the slice records 'the host has "
        "none' as an answer, not as a missing number"
    )
    assert "days" not in d["langfuse"]


def test_langfuse_probe_reports_the_daily_metrics_it_read(tmp_path):
    audit = _audit(tmp_path, [{"job_id": "jobA", "total_tokens": 10, "ts": "2026-10-20T00:00:00Z"}])
    with _LangfuseStub(LANGFUSE_DAILY_OK) as stub:
        r = _run(
            METRICS,
            "--json-summary",
            "--agent",
            AGENT,
            "--audit",
            str(audit),
            "--langfuse-url",
            stub.url,
            env_extra={
                "HERMES_LANGFUSE_PUBLIC_KEY": "pk-test-placeholder",
                "HERMES_LANGFUSE_SECRET_KEY": "sk-test-placeholder",
            },
        )
    d = _summary(r)
    assert d["langfuse"]["present"] is True
    assert d["langfuse"]["days"] == [
        {"date": "2026-10-23", "traces": 63, "cost_usd": 5.13393171382}
    ]
    assert stub.requests and "/api/public/metrics/daily" in stub.requests[0]["path"]
    assert stub.requests[0]["auth"].startswith("Basic "), "the metrics API is authenticated"
    for stream in (r.stdout, r.stderr):
        assert "sk-test-placeholder" not in stream, (
            "a credential must never reach the transcript that gets committed"
        )
