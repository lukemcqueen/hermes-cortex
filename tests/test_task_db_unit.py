"""L0 unit tests for task-db.py + task-mcp.py (design task-workflow.md §8).

Covers: build_query param escaping (injection regressions), allowlist
validation (`--agent "x' OR 1=1--"`, `$(whoami)`), arg parsing boundaries,
parse_row delimiter fuzz, pending JSON shape, Darwin/Linux branch argv,
repo/scope defaults, MCP tool registry + destructive-tool confirm gate.

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


def test_bad_uuid_rejected():
    _out, err, exc = _run_stdin_capture(
        task_db.cmd_update, "not-a-uuid", "completed")
    assert exc is not None and exc.code == 2


# ── parse_row fuzz (delimiter is '||') ─────────────────────────

_FIELD_IDX = {
    "id": 0, "content": 1, "agent": 2, "assignee": 3, "project": 4,
    "repo": 5, "target": 6, "scope": 7, "status": 8, "column": 9,
    "position": 10, "priority": 11, "due": 12, "tags": 13, "source": 14,
    "depends_on": 15, "session_id": 16, "created_at": 17, "updated_at": 18,
    "status_changed_at": 19, "completed_at": 20,
}


def _row_line(**overrides):
    fields = ["id1", "content", "agent", "assignee", "proj", "repo", "target",
              "personal", "pending", "todo", "0", "1", "2026-08-10T00:00:00Z",
              "t1,t2", "manual", "NULL", "sess1", "2026-08-06T00:00:00Z",
              "2026-08-06T00:00:00Z", "2026-08-06T00:00:00Z", "NULL"]
    for name, value in overrides.items():
        fields[_FIELD_IDX[name]] = value
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


def test_parse_row_short_line_none():
    assert task_db.parse_row("a||b") is None
    assert task_db.parse_row("") is None


def test_parse_row_delimiter_fuzz():
    """Content containing '||' (mangled by -F '||') must not crash parsing."""
    line = _row_line(content="content with || inside")
    row = task_db.parse_row(line)
    assert row is not None  # first 21 splits still parse; truncated content OK


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


# ── platform branch argv (no DB contact) ──────────────────────
# NOTE: _get_db_query is lru_cached per role — the platform branch resolves
# once per role per process. Tests must clear the cache before each branch.

def test_darwin_branch_direct_psql():
    task_db._get_db_query.cache_clear()
    with patch.object(platform, "system", return_value="Darwin"), \
         patch("os.path.exists", return_value=False):
        argv = task_db._get_db_query("mycortex_reader_esther")
    assert argv[0].endswith("psql")
    assert "-h" in argv and "127.0.0.1" in argv
    assert argv[argv.index("-U") + 1] == "mycortex_reader_esther"
    assert "ON_ERROR_STOP=1" in argv


def test_linux_branch_docker_exec():
    task_db._get_db_query.cache_clear()
    ok = SimpleNamespace(returncode=0)
    with patch.object(platform, "system", return_value="Linux"), \
         patch.object(task_db.subprocess, "run", return_value=ok):
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
    #          priority, due, tags, source, depends_on, session_id]
    assert params[4] == "hermes-cortex"
    assert params[7] == "personal"
    assert params[11] == "manual"


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
    """Without env, defaults must stay: mycortex DB + mycortex_reader_<profile>."""
    with patch.dict(os.environ, {}, clear=True):
        # resolve_profile falls back to hostname when no profile env is set
        with patch.object(platform, "node", return_value="l2testhost"):
            reloaded = _load("task_db_nodefault", TASK_DB_PATH)
            assert reloaded.DEFAULT_DB == "mycortex"
            assert reloaded.CRUD_ROLE == "mycortex_reader_l2testhost"


# ── MCP tool registry (task-mcp.py) ───────────────────────────

def test_mcp_tool_registry_and_confirm_gate():
    try:
        import mcp  # noqa: F401
    except ImportError:
        return  # mcp not installed in test env — registry untestable here
    task_mcp = _load("task_mcp", TASK_MCP_PATH)
    names = set(task_mcp._HANDLERS.keys())
    assert names == {"task_add", "task_list", "task_pending", "task_update",
                     "task_save_end", "task_prune"}

    # destructive tools refuse without confirm=true
    r = task_mcp._task_prune({"older_than": "1d"})
    assert r.isError and "confirm=true" in r.content[0].text
    r = task_mcp._task_save_end({})
    assert r.isError

    # task_add requires content
    r = task_mcp._task_add({})
    assert r.isError and "content" in r.content[0].text

    # unknown tool
    import asyncio
    r = asyncio.run(task_mcp.call_tool("task_nope", {}))
    assert r.isError
