"""L0 unit tests for task-db.py + task-mcp.py (design task-workflow.md §8).

Covers: build_query param escaping (injection regressions), allowlist
validation (`--agent "x' OR 1=1--"`, `$(whoami)`), arg parsing boundaries,
parse_row delimiter fuzz, pending JSON shape, Darwin/Linux branch argv,
repo/scope defaults, MCP tool registry + destructive-tool confirm gate.

TL-v2 (S3): parse_row 24 columns (parent_id/kind/correlation_id), paused
status, switch edge cases, --by-correlation, schema probe graceful
degradation, untrusted-inbox pending marking.

No-DB: importing task-db.py has zero DB contact (psql is lazy via lru_cache);
every test here is pure or mocks psql.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import platform
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
TASK_DB_PATH = REPO / "ops" / "scripts" / "manage" / "task-db.py"
TASK_MCP_PATH = REPO / "mcp-servers" / "task-mcp.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


task_db = _load("task_db", TASK_DB_PATH)


def _run_stdin_capture(fn, *args, **kwargs):
    """Run fn capturing stdout/stderr; return (out, err, exc)."""
    out, err = io.StringIO(), io.StringIO()
    exc = None
    try:
        with redirect_stdout(out), redirect_stderr(err):
            fn(*args, **kwargs)
    except SystemExit as e:
        exc = e
    return out.getvalue(), err.getvalue(), exc


# ── build_query escaping (B-1) ─────────────────────────────────

def test_build_query_quote_doubling():
    sql = task_db.build_query("SELECT ?", ["O'Brien's \"quote\""])
    assert sql == "SELECT 'O''Brien''s \"quote\"'"


def test_build_query_params_types():
    sql = task_db.build_query("SELECT ?, ?, ?, ?",
                              [None, True, 3, ["a", "b'c"]])
    assert sql == "SELECT NULL, TRUE, 3, ARRAY['a','b''c']"


def test_build_query_param_count_mismatch():
    try:
        task_db.build_query("SELECT ?", [1, 2])
        assert False, "expected ValueError for surplus params"
    except ValueError:
        pass
    try:
        task_db.build_query("SELECT ? ?", [1])
        assert False, "expected ValueError for missing params"
    except ValueError:
        pass


# ── Injection regressions (AC-4) ───────────────────────────────

def test_injection_agent_rejected():
    """--agent \"x' OR 1=1--\" must be rejected by the allowlist, not executed."""
    _out, err, exc = _run_stdin_capture(
        task_db.cmd_list, "x' OR 1=1--", None, None, None, None, None, None, None)
    assert exc is not None and exc.code == 2
    assert "invalid" in err.lower()


def test_injection_status_rejected():
    _out, err, exc = _run_stdin_capture(
        task_db.cmd_update, "00000000-0000-0000-0000-000000000000", "$(whoami)")
    assert exc is not None and exc.code == 2
    assert "invalid" in err.lower()


def test_injection_project_rejected():
    _out, err, exc = _run_stdin_capture(
        task_db.cmd_add, "content", None, 0, "proj; DROP TABLE tasks.tasks;--",
        None, None, None, None, None, [], "manual")
    assert exc is not None and exc.code == 2


def test_shell_payload_stored_as_literal():
    """$(whoami) in CONTENT (free text) is a literal, never executed."""
    with patch.object(task_db, "psql") as mock_psql:
        _out, _err, exc = _run_stdin_capture(
            task_db.cmd_add, "learn $(whoami) — literal", None, 1,
            None, None, None, None, None, None, [], "manual")
    assert exc is None
    params = mock_psql.call_args[0][1]
    assert params[1] == "learn $(whoami) — literal"


# ── Regression: fleet B-5 scrub gate degrades to personal (2026-08-21) ──
# cortex-bus-overnight task_add (scope=fleet, content with ~/.hermes/... paths)
# died with a raw RLS error ("new row violates row-level security policy for
# table tasks"). Fix: cmd_add probes tasks.content_ok_for_fleet() and degrades
# to scope=personal with a warning — the task is still created locally, the
# PII gate is never bypassed (the row simply never becomes fleet-visible).

def test_cmd_add_fleet_pathy_content_degrades_to_personal():
    """Fleet content with an abs-path smell → stored personal + warning."""
    with patch.object(task_db, "psql", side_effect=["f", ""]) as mock_psql:
        out, err, exc = _run_stdin_capture(
            task_db.cmd_add,
            "copy deployed ~/.hermes/skills/devops/x into repo", "esther", 1,
            None, None, None, "fleet", None, None, [], "inbox")
    assert exc is None
    assert "B-5 scrub gate" in err
    # probe fired once, then the upsert used scope='personal'
    assert mock_psql.call_count == 2
    upsert_params = mock_psql.call_args_list[1][0][1]
    assert upsert_params[7] == "personal"
    assert "✅ Task added" in out


def test_cmd_add_fleet_clean_content_stays_fleet():
    """Fleet content WITHOUT smells → stays fleet (no gate warning)."""
    with patch.object(task_db, "psql", side_effect=["t", ""]) as mock_psql:
        out, err, exc = _run_stdin_capture(
            task_db.cmd_add, "clean fleet task", "esther", 1,
            None, None, None, "fleet", None, None, [], "inbox")
    assert exc is None
    assert "B-5 scrub gate" not in err
    upsert_params = mock_psql.call_args_list[1][0][1]
    assert upsert_params[7] == "fleet"
    assert "stored LOCALLY on this host" in out


def test_cmd_add_personal_scope_skips_probe():
    """Personal scope never pays for the fleet-gate probe."""
    with patch.object(task_db, "psql", side_effect=[""]) as mock_psql:
        _out, _err, exc = _run_stdin_capture(
            task_db.cmd_add, "personal task", "esther", 1,
            None, None, None, "personal", None, None, [], "manual")
    assert exc is None
    assert mock_psql.call_count == 1  # upsert only, no content_ok_for_fleet probe


# ── Regression: long/multiline content mis-rendered (2026-08-21) ──
# task-db list/pending parse psql output line-by-line (||-delimited). A
# content value containing \n split the row across lines → parse_row got a
# short fragment → the row was DROPPED from list output (seen 3× as "stored
# garbled"). Fix: SELECT_COLS normalizes newlines to spaces for display;
# storage keeps the original bytes.

def test_select_cols_normalizes_content_newlines():
    """SELECT_COLS must flatten \\n/\\r in content so row parsing survives."""
    assert "regexp_replace(content" in task_db.SELECT_COLS
    assert "E'[\\n\\r]'" in task_db.SELECT_COLS


def test_parse_row_multiline_content_fragment_is_none():
    """A raw content with \\n (pre-fix) breaks || row parsing → row dropped.

    This documents WHY the SELECT-side normalization is load-bearing:
    cmd_list splits psql stdout on \\n first, so the fragment of a
    multiline row never has the 24 columns parse_row requires.
    """
    multiline = _row_line(content="line1\nline2 still content")
    fragment = multiline.split("\n")[0]  # what cmd_list feeds parse_row
    assert task_db.parse_row(fragment) is None
    # and the full (un-normalized) line as ONE line parses fine
    assert task_db.parse_row(multiline.replace("\n", " ")) is not None


def test_bad_uuid_rejected():
    _out, err, exc = _run_stdin_capture(
        task_db.cmd_update, "not-a-uuid", "completed")
    assert exc is not None and exc.code == 2


# ── parse_row fuzz (delimiter is '||', 24 columns in v2) ───────

_FIELD_IDX = {
    "id": 0, "content": 1, "agent": 2, "assignee": 3, "project": 4,
    "repo": 5, "target": 6, "scope": 7, "status": 8, "column": 9,
    "position": 10, "priority": 11, "due": 12, "tags": 13, "source": 14,
    "depends_on": 15, "session_id": 16, "created_at": 17, "updated_at": 18,
    "status_changed_at": 19, "completed_at": 20,
    "parent_id": 21, "kind": 22, "correlation_id": 23,
}


def _row_line(**overrides):
    fields = ["id1", "content", "agent", "assignee", "proj", "repo", "target",
              "personal", "pending", "todo", "0", "1", "2026-08-10T00:00:00Z",
              "t1,t2", "manual", "NULL", "sess1", "2026-08-06T00:00:00Z",
              "2026-08-06T00:00:00Z", "2026-08-06T00:00:00Z", "NULL",
              "NULL", "NULL", "NULL"]
    for name, value in overrides.items():
        fields[_FIELD_IDX[name]] = "NULL" if value is None else str(value)
    return "||".join(fields)


def test_parse_row_roundtrip():
    row = task_db.parse_row(_row_line())
    assert row["id"] == "id1"
    assert row["content"] == "content"
    assert row["scope"] == "personal"
    assert row["status"] == "pending"
    assert row["column"] == "todo"
    assert row["tags"] == ["t1", "t2"]
    assert row["source"] == "manual"
    assert row["assignee"] == "assignee"
    assert row["completed_at"] is None
    # v2 columns
    assert row["parent_id"] is None
    assert row["kind"] is None
    assert row["correlation_id"] is None


def test_parse_row_v2_fields():
    row = task_db.parse_row(_row_line(kind="slice", parent_id="story-1",
                                      correlation_id="corr-abc"))
    assert row["kind"] == "slice"
    assert row["parent_id"] == "story-1"
    assert row["correlation_id"] == "corr-abc"


def test_parse_row_short_line_none():
    assert task_db.parse_row("a||b") is None
    assert task_db.parse_row("") is None


def test_parse_row_delimiter_fuzz():
    """Content containing '||' (mangled by -F '||') must not crash parsing."""
    line = _row_line(content="content with || inside")
    row = task_db.parse_row(line)
    assert row is not None  # first 24 splits still parse; truncated content OK


def test_parse_row_non_ascii_and_percent():
    line = _row_line(content="한국어 100% ✓ && ||")
    row = task_db.parse_row(line)
    assert row is not None


# ── pending JSON shape (session restore) ──────────────────────

def test_pending_json_shape():
    fake = _row_line(id="uuid1", status="pending")
    with patch.object(task_db, "psql", return_value=fake):
        out, _err, exc = _run_stdin_capture(task_db.cmd_pending)
    assert exc is None
    items = json.loads(out)
    assert items[0]["id"] == "uuid1"
    assert items[0]["agent_name"] == "agent"
    assert items[0]["status"] == "pending"
    assert items[0]["project"] == "proj"
    assert items[0]["repo"] == "repo"
    assert items[0]["untrusted"] is False  # source=manual


def test_pending_inbox_rows_marked_untrusted():
    fake = _row_line(id="uuid9", source="inbox", correlation_id="corr-x")
    with patch.object(task_db, "psql", return_value=fake):
        out, _err, _exc = _run_stdin_capture(task_db.cmd_pending)
    items = json.loads(out)
    assert items[0]["untrusted"] is True
    assert items[0]["status"] == "pending"


def test_pending_includes_paused():
    fake = "\n".join([
        _row_line(id="u1", status="pending"),
        _row_line(id="u2", status="in_progress"),
        _row_line(id="u3", status="paused"),
        _row_line(id="u4", status="completed"),
    ])
    with patch.object(task_db, "psql", return_value=fake):
        out, _err, exc = _run_stdin_capture(task_db.cmd_pending)
    items = json.loads(out)
    statuses = {i["id"]: i["status"] for i in items}
    assert statuses == {"u1": "pending", "u2": "in_progress", "u3": "paused"}


def test_pending_filters_completed():
    fake = "\n".join([
        _row_line(id="u1", status="pending"),
        _row_line(id="u2", status="completed"),
        _row_line(id="u3", status="in_progress"),
    ])
    with patch.object(task_db, "psql", return_value=fake):
        out, _err, exc = _run_stdin_capture(task_db.cmd_pending)
    items = json.loads(out)
    ids = {i["id"] for i in items}
    assert ids == {"u1", "u3"}


# ── v3 (v008): blocked/waiting + story list --parent + summary ─

def test_pending_includes_blocked_waiting():
    fake = "\n".join([
        _row_line(id="u1", status="blocked"),
        _row_line(id="u2", status="waiting"),
        _row_line(id="u3", status="completed"),
    ])
    with patch.object(task_db, "psql", return_value=fake):
        out, _err, exc = _run_stdin_capture(task_db.cmd_pending)
    items = json.loads(out)
    statuses = {i["id"]: i["status"] for i in items}
    assert statuses == {"u1": "blocked", "u2": "waiting"}


def test_update_blocked_requires_v3_schema():
    with patch.object(task_db, "schema_version", return_value=5):
        _out, err, exc = _run_stdin_capture(
            task_db.cmd_update, "00000000-0000-0000-0000-000000000000", "blocked")
    assert exc is not None and exc.code == 2
    assert "v8" in err


def test_update_blocked_ok_on_v8_schema():
    with patch.object(task_db, "schema_version", return_value=8), \
            patch.object(task_db, "psql", return_value="ok"):
        _out, _err, exc = _run_stdin_capture(
            task_db.cmd_update, "00000000-0000-0000-0000-000000000000", "waiting")
    assert exc is None


def test_list_parent_requires_v3_schema():
    with patch.object(task_db, "schema_version", return_value=5):
        _out, err, exc = _run_stdin_capture(
            task_db.cmd_list, None, None, None, None, None, None, None, None,
            "00000000-0000-0000-0000-000000000000")
    assert exc is not None and exc.code == 2
    assert "v8" in err


def test_list_parent_bad_uuid_rejected():
    with patch.object(task_db, "schema_version", return_value=8):
        _out, err, exc = _run_stdin_capture(
            task_db.cmd_list, None, None, None, None, None, None, None, None,
            "not-a-uuid")
    assert exc is not None and exc.code == 2


def test_summary_requires_story_and_v3():
    # old schema → refused
    with patch.object(task_db, "schema_version", return_value=5):
        _out, err, exc = _run_stdin_capture(
            task_db.cmd_summary, "00000000-0000-0000-0000-000000000000")
    assert exc is not None and exc.code == 2
    assert "v8" in err
    # bad uuid → refused
    with patch.object(task_db, "schema_version", return_value=8):
        _out, _err, exc = _run_stdin_capture(task_db.cmd_summary, "nope")
    assert exc is not None and exc.code == 2


def test_summary_prints_json_fields():
    fake = json.dumps({
        "story_id": "00000000-0000-0000-0000-000000000001",
        "content": "S9: test story", "status": "pending", "priority": 2,
        "scope": "personal", "created_by": "esther", "total_slices": 2,
        "pending": 1, "in_progress": 0, "paused": 0, "blocked": 0,
        "waiting": 0, "completed": 1, "cancelled": 0, "active": 1,
        "done_ratio": 50.0,
    })
    with patch.object(task_db, "schema_version", return_value=8), \
            patch.object(task_db, "psql", return_value=fake):
        out, _err, exc = _run_stdin_capture(
            task_db.cmd_summary, "00000000-0000-0000-0000-000000000001")
    assert exc is None
    assert "S9: test story" in out
    assert "2 total" in out
    assert "1 done + 0 cancelled" in out


def test_summary_empty_result_fails():
    with patch.object(task_db, "schema_version", return_value=8), \
            patch.object(task_db, "psql", return_value=""):
        _out, err, exc = _run_stdin_capture(
            task_db.cmd_summary, "00000000-0000-0000-0000-000000000001")
    assert exc is not None and exc.code == 1
    assert "no story" in err.lower()


# ── restore: untrusted-inbox skip (R-4) ───────────────────────

def test_restore_skips_untrusted_by_default(tmp_path):
    """Inbox-derived rows must NOT be restored into agent context by default."""
    data = [
        {"id": "11111111-1111-1111-1111-111111111111", "content": "inbox row",
         "agent_name": "esther", "status": "pending", "scope": "personal",
         "untrusted": True},
        {"id": "22222222-2222-2222-2222-222222222222", "content": "manual row",
         "agent_name": "esther", "status": "pending", "scope": "personal",
         "untrusted": False},
    ]
    f = tmp_path / "pending.json"
    f.write_text(json.dumps(data))
    with patch.object(task_db, "psql") as mock_psql:
        out, _err, _exc = _run_stdin_capture(task_db.cmd_restore, str(f))
    assert "Restored 1 task(s)" in out
    assert "skipped 1 untrusted" in out
    # Only the manual row reached task_upsert
    assert mock_psql.call_count == 1
    assert mock_psql.call_args[0][1][1] == "manual row"


def test_restore_include_inbox(tmp_path):
    data = [
        {"id": "11111111-1111-1111-1111-111111111111", "content": "inbox row",
         "agent_name": "esther", "status": "pending", "scope": "personal",
         "untrusted": True},
    ]
    f = tmp_path / "pending.json"
    f.write_text(json.dumps(data))
    with patch.object(task_db, "psql") as mock_psql:
        out, _err, _exc = _run_stdin_capture(
            task_db.cmd_restore, str(f), True)
    assert "Restored 1 task(s)" in out
    assert "skipped" not in out
    assert mock_psql.call_count == 1


# ── switch edge cases (M-8) ───────────────────────────────────

def test_switch_rejects_story_target():
    """Switching to a story is rejected — you resume slices, not stories."""
    story_row = _row_line(id="33333333-3333-3333-3333-333333333333",
                          kind="story", status="in_progress")
    with patch.object(task_db, "psql", side_effect=["", story_row]), \
         patch.object(task_db, "schema_version", return_value=5):
        out, err, exc = _run_stdin_capture(
            task_db.cmd_switch, "33333333-3333-3333-3333-333333333333")
    assert exc is not None and exc.code == 2
    assert "story" in err.lower()


def test_switch_same_task_noop():
    """target == current in_progress → friendly no-op, no DB writes."""
    tid = "44444444-4444-4444-4444-444444444444"
    row = _row_line(id=tid, kind=None, status="in_progress")
    with patch.object(task_db, "psql", side_effect=[tid, row]) as mock_psql, \
         patch.object(task_db, "schema_version", return_value=5):
        out, _err, exc = _run_stdin_capture(task_db.cmd_switch, tid)
    assert exc is None
    assert "no-op" in out.lower()
    assert mock_psql.call_count == 2  # current lookup + target lookup only


def test_switch_resume_without_current():
    """No active task → just resume the target (single upsert)."""
    tid = "55555555-5555-5555-5555-555555555555"
    row = _row_line(id=tid, kind=None, status="pending")
    with patch.object(task_db, "psql", side_effect=["", row, ""]) as mock_psql, \
         patch.object(task_db, "schema_version", return_value=5):
        out, _err, exc = _run_stdin_capture(task_db.cmd_switch, tid)
    assert exc is None
    assert "Resumed" in out
    assert mock_psql.call_count == 3  # current + target + upsert


def test_switch_pauses_current_and_resumes_target():
    """Active task + different target → two upserts with reason='switch'."""
    cur = "66666666-6666-6666-6666-666666666666"
    tgt = "77777777-7777-7777-7777-777777777777"
    row = _row_line(id=tgt, kind=None, status="pending")
    with patch.object(task_db, "psql", side_effect=[cur, row, ""]) as mock_psql, \
         patch.object(task_db, "schema_version", return_value=5):
        out, _err, exc = _run_stdin_capture(task_db.cmd_switch, tgt)
    assert exc is None
    assert "Switched" in out
    # The combined transaction query: GUC + pause current + resume target
    combined = mock_psql.call_args_list[2][0][0]
    assert "transition_reason" in combined and "'switch'" in combined
    assert "paused" in combined and "in_progress" in combined


# ── by-correlation update (R-19) ──────────────────────────────

def test_update_by_correlation_resolves_id():
    corr = "corr-test-1"
    resolved_id = "88888888-8888-8888-8888-888888888888"
    with patch.object(task_db, "psql",
                      side_effect=[resolved_id, ""]) as mock_psql, \
         patch.object(task_db, "schema_version", return_value=5):
        out, _err, exc = _run_stdin_capture(
            task_db.cmd_update, "", "in_progress", None, corr, True)
    assert exc is None
    # first call: lookup by correlation; second: the upsert with resolved id
    assert mock_psql.call_args_list[1][0][1][0] == resolved_id


def test_update_by_correlation_not_found():
    with patch.object(task_db, "psql", return_value=""), \
         patch.object(task_db, "schema_version", return_value=5):
        out, err, exc = _run_stdin_capture(
            task_db.cmd_update, "", "completed", None, "corr-missing", True)
    assert exc is not None and exc.code == 1
    assert "no inbox task" in err.lower()


# ── schema probe graceful degradation (R-11) ──────────────────

def test_schema_version_parses_int():
    with patch.object(task_db, "psql", return_value="5"):
        assert task_db.schema_version() == 5


def test_schema_version_zero_on_missing():
    with patch.object(task_db, "psql", return_value=""):
        assert task_db.schema_version() == 0


def test_v2_feature_rejected_on_old_schema():
    with patch.object(task_db, "psql", return_value="4"):
        _out, err, exc = _run_stdin_capture(task_db._require_v2, "switch")
    assert exc is not None and exc.code == 2
    assert "v5" in err


def test_paused_requires_v2():
    with patch.object(task_db, "psql", return_value="4"):
        _out, err, exc = _run_stdin_capture(
            task_db.cmd_update, "00000000-0000-0000-0000-000000000000", "paused")
    assert exc is not None and exc.code == 2
    assert "v5" in err


# ── platform branch argv (no DB contact) ──────────────────────
# NOTE: _get_db_query is lru_cached per role — the platform branch resolves
# once per role per process. Tests must clear the cache before each branch.

def test_darwin_branch_direct_psql():
    task_db._get_db_query.cache_clear()
    with patch.object(platform, "system", return_value="Darwin"), \
         patch("os.path.exists", return_value=False):
        argv = task_db._get_db_query("mycortex_reader_esther")
    # Darwin uses the same trust-auth docker exec path as Linux — no pgpass
    # dependency (scratch DBs like mycortex_test have no .pgpass entry).
    assert argv[0] == "docker"
    assert "psql" in argv
    assert "-h" not in argv and "127.0.0.1" not in argv
    assert argv[argv.index("-U") + 1] == "mycortex_reader_esther"
    assert "ON_ERROR_STOP=1" in argv


def test_linux_branch_docker_exec():
    task_db._get_db_query.cache_clear()
    with patch.object(platform, "system", return_value="Linux"), \
         patch.object(task_db.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
        argv = task_db._get_db_query("mycortex_reader_esther")
    assert argv[0] == "docker"
    assert "ON_ERROR_STOP=1" in argv


def test_linux_branch_sg_fallback_no_user_data():
    """sg fallback command string must contain NO user data (B-1)."""
    task_db._get_db_query.cache_clear()
    with patch.object(platform, "system", return_value="Linux"), \
         patch.object(task_db.subprocess, "run",
                      side_effect=FileNotFoundError("docker")):
        argv = task_db._get_db_query("mycortex_reader_esther")
    joined = " ".join(argv)
    assert joined.startswith("sg docker -c")
    assert "mycortex_reader_esther" in joined  # role is fixed, not user data
    assert "-F '||'" in joined  # shell-quoted separator — unquoted || is shell OR


# ── repo/scope defaults ───────────────────────────────────────

def test_add_defaults_project_scope_source():
    with patch.object(task_db, "psql") as mock_psql:
        _out, _err, exc = _run_stdin_capture(
            task_db.cmd_add, "some task", None, 0, None, None, None, None,
            None, None, [], None)
    assert exc is None
    params = mock_psql.call_args[0][1]
    # params: [id, content, agent, assignee, project, repo, target, scope,
    #          priority, due, tags, source, depends_on, session_id, parent, kind, corr]
    assert params[4] == "hermes-cortex"
    assert params[7] == "personal"
    assert params[11] == "manual"


def test_add_with_parent_kind():
    story = "99999999-9999-9999-9999-999999999999"
    with patch.object(task_db, "psql") as mock_psql, \
         patch.object(task_db, "schema_version", return_value=5):
        _out, _err, exc = _run_stdin_capture(
            task_db.cmd_add, "slice task", None, 0, None, None, None, None,
            None, None, [], "manual", story, "slice")
    assert exc is None
    params = mock_psql.call_args[0][1]
    assert params[14] == story  # parent
    assert params[15] == "slice"  # kind


def test_priority_bounds():
    _out, err, exc = _run_stdin_capture(
        task_db.cmd_add, "x", None, 9, None, None, None, None, None, None, [], "manual")
    assert exc is not None and exc.code == 2


# ── env overrides (L2 fleet-test hermeticity) ────────────────

def test_env_overrides_task_db_name_and_role():
    """TASK_DB_NAME / TASK_DB_ROLE must exist — L2 test-task-fleet.sh runs
    CRUD against a scratch DB + scratch role via these. A future edit that
    removes them silently re-points fleet tests at the LIVE mycortex DB."""
    with patch.dict(os.environ, {"TASK_DB_NAME": "fleet_test",
                                 "TASK_DB_ROLE": "mycortex_reader"}, clear=False):
        reloaded = _load("task_db_env", TASK_DB_PATH)
        assert reloaded.DEFAULT_DB == "fleet_test"
        assert reloaded.CRUD_ROLE == "mycortex_reader"


def test_env_overrides_defaults_when_unset():
    """Without env AND without .env agent file → hard error, NO hostname fallback.
    (Luke 2026-08-10: identity is explicit or the tool fails.)"""
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(Path, "is_file", return_value=False), \
             patch.object(Path, "read_text",
                          side_effect=OSError("no file")):
            try:
                _load("task_db_nodefault", TASK_DB_PATH)
                assert False, "expected SystemExit when no identity configured"
            except SystemExit as e:
                assert e.code == 1


def test_env_agent_name_reads_dotenv():
    """The .env agent variable is the identity source — never whoami/hostname."""
    with patch.object(Path, "is_file", return_value=True), \
         patch.object(Path, "read_text",
                      return_value="# header\nAGENT_NAME=gisu\nOTHER=1\n"):
        assert task_db._env_agent_name() == "gisu"


# ── MCP tool registry (task-mcp.py) ───────────────────────────

def test_mcp_tool_registry_and_confirm_gate():
    try:
        import mcp  # noqa: F401
    except ImportError:
        return  # mcp not installed in test env — registry untestable here
    task_mcp = _load("task_mcp", TASK_MCP_PATH)
    names = set(task_mcp._HANDLERS.keys())
    assert names == {"task_add", "task_list", "task_pending", "task_update",
                     "task_switch", "task_save_end", "task_prune",
                     "task_claim", "task_unclaim", "task_list_claimable",
                     "task_board", "task_report", "task_verify"}

    # destructive tools refuse without confirm=true
    r = task_mcp._task_prune({"older_than": "1d"})
    assert r.is_error and "confirm=true" in r.content[0].text
    r = task_mcp._task_save_end({})
    assert r.is_error

    # task_add requires content
    r = task_mcp._task_add({})
    assert r.is_error and "content" in r.content[0].text

    # task_switch requires task_id
    r = task_mcp._task_switch({})
    assert r.is_error and "task_id" in r.content[0].text

    # unknown tool
    import asyncio
    r = asyncio.run(task_mcp.call_tool("task_nope", {}))
    assert r.is_error


# ── Derived overdue flag (due passed on an open status) ──

def test_due_overdue_past_date_open_status():
    assert task_db._is_due_overdue("2020-01-01T00:00:00Z", "pending") is True
    assert task_db._is_due_overdue("2020-01-01T00:00:00Z", "in_progress") is True
    assert task_db._is_due_overdue("2020-01-01T00:00:00Z", "paused") is True


def test_due_overdue_future_date():
    assert task_db._is_due_overdue("2999-01-01T00:00:00Z", "pending") is False


def test_due_overdue_terminal_status_never():
    assert task_db._is_due_overdue("2020-01-01T00:00:00Z", "completed") is False
    assert task_db._is_due_overdue("2020-01-01T00:00:00Z", "cancelled") is False


def test_due_overdue_missing_or_malformed():
    assert task_db._is_due_overdue(None, "pending") is False
    assert task_db._is_due_overdue("", "pending") is False
    assert task_db._is_due_overdue("not-a-date", "pending") is False


def test_due_overdue_naive_datetime_utc():
    # naive timestamps (psql -t -A prints "YYYY-MM-DD HH:MM:SS+00") parse
    assert task_db._is_due_overdue("2020-01-01 00:00:00+00", "in_progress") is True
