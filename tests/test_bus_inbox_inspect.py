"""Tests for ops/scripts/orch-bus/bus-inbox-inspect.py.

The inspector parses the bus's queue/peek payloads into a health transcript.
These tests pin the parsing contract that the cron note relies on:

  * summarize_queues flags every DLQ and every non-empty queue, and a fully
    idle fleet is reported as no non-empty queues beyond the DLQ list
    (the quiet case must not be misreported as a backlog).
  * inspect() keeps EVERY message in a peek — the historical bug dropped all
    but the last message and always reported count=0, which would hide a
    backlog and make a "queue is clear" claim false.

No network: _http_get is monkeypatched.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

MOD_PATH = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "orch-bus" / "bus-inbox-inspect.py"
BASE = "http://127.0.0.1:8903"


def _load():
    spec = importlib.util.spec_from_file_location("bus_inbox_inspect", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bus_inbox_inspect"] = mod
    spec.loader.exec_module(mod)
    return mod


QUEUES = {
    "total": 4,
    "queues": [
        {"name": "inbox_esther", "depth": 0, "processing": 0, "dlq": False, "parent": None},
        {"name": "inbox_orchestrator", "depth": 2, "processing": 0, "dlq": False, "parent": None},
        {"name": "inbox_orchestrator_dlq", "depth": 0, "processing": 0, "dlq": True,
         "parent": "inbox_orchestrator"},
        {"name": "out_esther", "depth": 0, "processing": 0, "dlq": False, "parent": None},
    ],
}

PEEK = {
    "messages": [
        {"msg_id": "aaa", "enqueued_at": "2026-10-08T11:50Z", "read_ct": None,
         "body": {"from": "esther", "to": "moses", "subject": "DOCTOR_TEST"}},
        {"msg_id": "bbb", "enqueued_at": "2026-10-08T11:52Z", "read_ct": None,
         "body": {"from": "esther", "to": "moses", "subject": "HEALTH_PERSISTENT_ISSUES",
                  "body": {"mirrored_from_queue": "inbox_health_check",
                           "primary_msg_id": "p1", "original_body": "{}"}}},
    ],
}


def test_summarize_queues_flags_dlq_and_nonempty():
    mod = _load()
    s = mod.summarize_queues(QUEUES)
    assert s["queue_total"] == 4
    names = {q["name"] for q in s["nonempty"]}
    # non-empty queue AND the DLQ row (any *_dlq is always listed)
    assert names == {"inbox_orchestrator", "inbox_orchestrator_dlq"}
    assert [d["name"] for d in s["dlq"]] == ["inbox_orchestrator_dlq"]


def test_summarize_queues_quiet_fleet():
    mod = _load()
    quiet = {"total": 1, "queues": [
        {"name": "inbox_esther", "depth": 0, "processing": 0, "dlq": False, "parent": None}]}
    assert mod.summarize_queues(quiet)["nonempty"] == []


def _with_fake_get(mod, fake):
    """Swap _http_get without pytest's monkeypatch fixture (offline-runnable)."""
    original = mod._http_get
    mod._http_get = fake
    return original


def test_inspect_keeps_every_message():
    mod = _load()

    def fake_get(base, path):
        return QUEUES if path.endswith("/queues") else PEEK

    original = _with_fake_get(mod, fake_get)
    try:
        out = mod.inspect("local", BASE, "esther")
    finally:
        mod._http_get = original
    orch = out["peeks"]["inbox_orchestrator"]
    # regression: must be 2, not 0 (old code reported len([]))
    assert orch["count"] == 2
    assert [m["msg_id"] for m in orch["messages"]] == ["aaa", "bbb"]
    # mirror envelope is unwrapped into the entry
    assert orch["messages"][1]["mirrored_from_queue"] == "inbox_health_check"
    assert orch["messages"][1]["primary_msg_id"] == "p1"


def test_inspect_reports_peek_errors():
    mod = _load()

    def fake_get(base, path):
        if path.endswith("/queues"):
            return QUEUES
        return {"_http_error": 403}

    original = _with_fake_get(mod, fake_get)
    try:
        out = mod.inspect("local", BASE, "esther")
    finally:
        mod._http_get = original
    assert out["peeks"]["out_esther"] == {"error": {"_http_error": 403}}


CLEAN_REPORT = {
    "agent": "esther",
    "buses": [
        {"label": "local", "dlq": [{"name": "inbox_esther_dlq", "depth": 0, "processing": 0}],
         "nonempty": [{"name": "inbox_esther_dlq", "depth": 0, "dlq": True}]},
        {"label": "primary", "dlq": [{"name": "inbox_orchestrator_dlq", "depth": 0, "processing": 0}],
         "nonempty": [{"name": "inbox_orchestrator_dlq", "depth": 0, "dlq": True}]},
    ],
    "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
    "failover": {"failover_active": False},
}


def test_fleet_issues_clean_report_is_empty():
    """The no-action / silent condition is exactly fleet_issues() == []."""
    mod = _load()
    assert mod.fleet_issues(CLEAN_REPORT) == []


def test_fleet_issues_flags_dlq_and_own_inbox():
    mod = _load()
    bad = {
        "agent": "esther",
        "buses": [{
            "label": "local",
            "dlq": [{"name": "inbox_esther_dlq", "depth": 3, "processing": 1}],
            "nonempty": [{"name": "inbox_esther", "depth": 12, "dlq": False}],
        }],
        "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
        "failover": {"failover_active": False},
    }
    issues = mod.fleet_issues(bad, now=NOW)
    assert any("BLOCKED (DLQ) inbox_esther_dlq" in i for i in issues)
    # depth>0 with no dated peek => surfaced, never silently 'clean'
    assert any("undated pending inbox_esther depth=12" in i for i in issues)


def test_fleet_issues_flags_dlq_and_own_inbox_fresh():
    """Own inbox with FRESH messages is reported as unprocessed (not stale)."""
    mod = _load()
    bad = {
        "agent": "esther",
        "buses": [{
            "label": "local", "inspection_error": None, "dlq": [],
            "nonempty": [{"name": "inbox_esther", "depth": 1, "dlq": False}],
            "peeks": {"inbox_esther": {"count": 1, "messages": [
                {"msg_id": "M", "enqueued_at": "2026-10-08T11:59:00+00:00"}]}},
        }],
        "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
        "failover": {"failover_active": False},
    }
    issues = mod.fleet_issues(bad, now=NOW)
    assert issues == ["local: unprocessed inbox_esther depth=1"]


def test_pipeline_queues_do_not_raise_issues():
    """Fresh (< STALE_HOURS) pipeline traffic must not flap the check."""
    mod = _load()
    report = {
        "agent": "esther",
        "buses": [{
            "label": "local", "inspection_error": None,
            "dlq": [{"name": "inbox_esther_dlq", "depth": 0, "processing": 0}],
            "nonempty": [{"name": "inbox_orchestrator", "depth": 2, "dlq": False},
                         {"name": "out_esther", "depth": 2, "dlq": False},
                         {"name": "inbox_esther_dlq", "depth": 0, "dlq": True}],
            "peeks": {
                "inbox_orchestrator": {"count": 2, "messages": [
                    {"msg_id": "a", "enqueued_at": "2026-10-08T11:58:00+00:00"},
                    {"msg_id": "b", "enqueued_at": "2026-10-08T11:59:00+00:00"}]},
                "out_esther": {"count": 2, "messages": [
                    {"msg_id": "c", "enqueued_at": "2026-10-08T11:50:00+00:00"},
                    {"msg_id": "d", "enqueued_at": "2026-10-08T11:51:00+00:00"}]},
            },
        }],
        "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
        "failover": {"failover_active": False},
    }
    assert mod.fleet_issues(report, now=NOW) == []


def test_fleet_issues_flags_missing_forwarder_and_active_failover():
    mod = _load()
    bad = {"buses": [], "forwarder": {}, "failover": {"failover_active": True}}
    issues = mod.fleet_issues(bad)
    assert "forwarder: no last_run recorded" in issues
    assert "failover: ACTIVE" in issues


def test_backlog_visible_beyond_peek_window():
    """Depth is reported exactly even when it exceeds the peek window."""
    mod = _load()
    deep = {"total": 1, "queues": [
        {"name": "inbox_esther", "depth": mod.PEEK_LIMIT + 100, "processing": 0,
         "dlq": False, "parent": None}]}
    s = mod.summarize_queues(deep)
    assert s["nonempty"][0]["depth"] == mod.PEEK_LIMIT + 100


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bus-inbox-report-redacted.json"


def test_committed_fixture_flags_stale_out_esther():
    """The redacted real snapshot's known 6-day out_esther backlog is flagged."""
    mod = _load()
    report = json.loads(FIXTURE.read_text())
    issues = mod.fleet_issues(report, now=NOW)
    assert issues == [
        "local: stale pending out_esther — 2 msg(s), "
        "oldest 2026-10-02T08:10:00.143776+00:00"
    ]


def test_urgent_message_is_an_issue_even_when_fresh():
    mod = _load()
    report = {"agent": "esther",
              "buses": [{"label": "local", "inspection_error": None, "dlq": [], "nonempty": [],
                         "peeks": {"inbox_esther": {"count": 1, "messages": [
                             {"msg_id": "M", "enqueued_at": "2026-10-08T11:59:00+00:00",
                              "priority": 90}]}}}],
              "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
              "failover": {"failover_active": False}}
    issues = mod.fleet_issues(report, now=NOW)
    assert any("urgent inbox_esther" in i and "priority>=50" in i for i in issues)


def test_normal_priority_fresh_message_is_not_urgent():
    mod = _load()
    report = {"agent": "esther",
              "buses": [{"label": "local", "inspection_error": None, "dlq": [], "nonempty": [],
                         "peeks": {"inbox_orchestrator": {"count": 1, "messages": [
                             {"msg_id": "M", "enqueued_at": "2026-10-08T11:59:00+00:00",
                              "priority": 0}]}}}],
              "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
              "failover": {"failover_active": False}}
    assert mod.fleet_issues(report, now=NOW) == []


def test_nonempty_dlq_is_reported_as_blocked():
    mod = _load()
    report = {"agent": "esther",
              "buses": [{"label": "primary", "inspection_error": None,
                         "dlq": [{"name": "inbox_gisu_dlq", "depth": 2, "processing": 0}],
                         "nonempty": [], "peeks": {}}],
              "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
              "failover": {"failover_active": False}}
    issues = mod.fleet_issues(report, now=NOW)
    assert issues == ["primary: BLOCKED (DLQ) inbox_gisu_dlq depth=2 processing=0"]


def test_stale_message_in_any_queue_is_an_issue():
    mod = _load()
    report = {"agent": "esther",
              "buses": [{"label": "primary", "inspection_error": None, "dlq": [], "nonempty": [],
                         "peeks": {"inbox_health_check": {"count": 1, "messages": [
                             {"msg_id": "M", "enqueued_at": "2026-10-01T12:00:00+00:00"}]}}}],
              "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
              "failover": {"failover_active": False}}
    issues = mod.fleet_issues(report, now=NOW)
    assert any("stale pending inbox_health_check" in i for i in issues)


def test_fresh_messages_are_not_stale():
    mod = _load()
    report = {"agent": "esther",
              "buses": [{"label": "local", "inspection_error": None, "dlq": [], "nonempty": [],
                         "peeks": {"inbox_orchestrator": {"count": 1, "messages": [
                             {"msg_id": "M", "enqueued_at": "2026-10-08T11:59:00+00:00"}]}}}],
              "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
              "failover": {"failover_active": False}}
    assert mod.fleet_issues(report, now=NOW) == []


def test_undated_pending_queue_is_surfaced():
    """depth>0 with no dated peek must not read as clean."""
    mod = _load()
    report = {"agent": "esther",
              "buses": [{"label": "local", "inspection_error": None, "dlq": [],
                         "nonempty": [{"name": "inbox_gisu", "depth": 5, "dlq": False}],
                         "peeks": {"inbox_gisu": {"error": {"_http_error": 403}}}}],
              "forwarder": {"last_run": "2026-10-08T12:00:00Z"},
              "failover": {"failover_active": False}}
    assert any("undated pending inbox_gisu depth=5" in i
               for i in mod.fleet_issues(report, now=NOW))


def test_fixture_peek_counts_match_messages():
    """Fixture integrity: every peek count == len(messages) (no phantom counts)."""
    report = json.loads(FIXTURE.read_text())
    for bus in report["buses"]:
        for qn, peek in bus["peeks"].items():
            assert peek["count"] == len(peek["messages"]), f"{bus['label']}:{qn}"


def test_inspection_error_is_an_issue():
    """A failed inspection must never read as a clean fleet."""
    mod = _load()
    report = {"agent": "esther",
              "buses": [{"label": "primary", "base": "redacted",
                         "inspection_error": "queue fetch failed: {'_http_error': 401}"}],
              "forwarder": {"last_run": "t"}, "failover": {"failover_active": False}}
    issues = mod.fleet_issues(report)
    assert any("INSPECTION FAILED" in i for i in issues)


def test_inspect_marks_queue_fetch_failure():
    mod = _load()

    def fake_get(base, path):
        return {"_http_error": 401}

    original = _with_fake_get(mod, fake_get)
    try:
        out = mod.inspect("primary", "redacted", "esther")
    finally:
        mod._http_get = original
    assert out["inspection_error"] and "401" in out["inspection_error"]
    assert out["nonempty"] == [] and out["dlq"] == []


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
