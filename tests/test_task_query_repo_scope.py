#!/usr/bin/env python3
"""Repo scoping for task QUERIES (cycle 12593, task-query-repo-scope).

The bug (reported by Titus): task_pending / task_list / task_board / the queue
views returned EVERY repo's tasks for an agent, so agents picked up and
reported work belonging to another repository. This file pins the contract:

  * the repo is resolved from the caller's own session identity
    (explicit arg -> injected repo_path/repo_slug -> CORTEX_SESSION_REPO -> the
    MCP child's cwd git repo);
  * an UNRESOLVABLE repo returns NO tasks (operator rule, 2026-10-14) — never
    "all repos";
  * a scoped query returns ONLY the caller's own repo (`repo = ?`); untagged
    (legacy) rows are NOT included — they are opt-in via `include_untagged`
    (CLI `--include-untagged`), and a NAMED repo's rows never leak in;
  * the fleet-wide view exists ONLY as an explicit opt-in (`repo="ALL"`);
  * a task MINTED with no `--repo` from a session whose repo resolves inherits
    that repo, so a strict default never hides the caller's own new work.

Run: python3 -m pytest tests/test_task_query_repo_scope.py -q
Hermetic: no DB contact — psql is mocked at the module boundary.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
TASK_DB_PATH = REPO / "ops" / "scripts" / "manage" / "task-db.py"
TASK_MCP_PATH = REPO / "mcp-servers" / "task-mcp.py"
SESSION_REPO_PATH = REPO / "ops" / "scripts" / "cortex_lib" / "session_repo.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


task_db = _load("task_db_scope", TASK_DB_PATH)


def _run_capture(fn, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    exc = None
    try:
        with redirect_stdout(out), redirect_stderr(err):
            fn(*args, **kwargs)
    except SystemExit as e:
        exc = e
    return out.getvalue(), err.getvalue(), exc


def _row_line(**over):
    """One ||-delimited row shaped like SELECT_COLS output (24 fields)."""
    parts = ["uuid1", "content", "agent", "", "proj", "repo",
             "", "personal", "pending", "", "0", "1",
             "", "", "manual", "", "", "2026-10-14 09:00:00+00",
             "2026-10-14 09:00:00+00", "2026-10-14 09:00:00+00", "",
             "", "", ""]
    idx = {"id": 0, "content": 1, "agent": 2, "project": 4, "repo": 5,
           "scope": 7, "status": 8, "source": 14, "correlation_id": 23}
    for k, v in over.items():
        parts[idx[k]] = v
    return "||".join(parts)


def _git_init(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True,
                   capture_output=True)
    return path


# ── resolution ladder ───────────────────────────────────────────

def test_explicit_repo_wins_over_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_REPO", "from-env")
    r = task_db.resolve_query_repo("explicit-repo")
    assert r is not None and r.slug == "explicit-repo" and r.source == "explicit"


def test_injected_repo_path_wins_over_env(tmp_path, monkeypatch):
    root = _git_init(tmp_path / "project-a")
    monkeypatch.setenv("CORTEX_SESSION_REPO", "from-env")
    r = task_db.resolve_query_repo(None, repo_path=str(root))
    assert r is not None and r.slug == "project-a" and r.source == "injected"


def test_injected_repo_slug_is_honoured(monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    r = task_db.resolve_query_repo(None, repo_slug="steadfaste")
    assert r is not None and r.slug == "steadfaste" and r.source == "injected"


def test_injected_repo_path_must_be_a_real_git_repo(tmp_path, monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    monkeypatch.chdir(tmp_path)
    r = task_db.resolve_query_repo(None, repo_path=str(plain))
    assert r is None, "a non-git path must not become a repo identity"


def test_env_name_form_is_used_as_declared_slug(monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_REPO", "steadfaste")
    r = task_db.resolve_query_repo()
    assert r is not None and r.slug == "steadfaste" and r.source == "env"


def test_env_absolute_path_form_uses_basename(tmp_path, monkeypatch):
    root = _git_init(tmp_path / "project-b")
    monkeypatch.setenv("CORTEX_SESSION_REPO", str(root))
    r = task_db.resolve_query_repo()
    assert r is not None and r.slug == "project-b" and r.source == "env"


def test_cwd_git_repo_is_the_last_resort(tmp_path, monkeypatch):
    root = _git_init(tmp_path / "project-c")
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    monkeypatch.chdir(root)
    r = task_db.resolve_query_repo()
    assert r is not None and r.slug == "project-c" and r.source == "cwd"


def test_unknown_repo_resolves_to_none(tmp_path, monkeypatch):
    """No explicit arg, no injection, no env, cwd not a git repo -> None."""
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    monkeypatch.chdir(tmp_path)
    assert task_db.resolve_query_repo() is None


def test_git_missing_is_could_not_verify_not_a_crash(tmp_path, monkeypatch):
    """A host without git (or a repo-less cwd) must fail CLOSED — no traceback."""
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    monkeypatch.chdir(tmp_path)

    def no_git(*a, **kw):
        raise FileNotFoundError("git not installed")

    monkeypatch.setattr(task_db.subprocess, "check_output", no_git)
    assert task_db.resolve_query_repo() is None


def test_invalid_explicit_repo_label_fails_closed():
    """A path-ish / injection-y label is NOT a repo identity — and never falls
    through to a broader scope."""
    for bad in ("../etc", "a/b", "x' OR 1=1--", "$(whoami)", ""):
        r = task_db.resolve_query_repo(bad)
        assert r is None or r.slug != bad, bad


def test_cli_rejects_a_bad_repo_label_with_a_usable_message(tmp_path, monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    monkeypatch.chdir(tmp_path)
    _out, err, exc = _run_capture(
        task_db.cmd_list, None, None, None, None, "../etc", None, None, None)
    assert exc is not None and exc.code == 2
    assert "--repo" in err and "invalid" in err


def test_repo_all_declares_a_fleet_view():
    r = task_db.resolve_query_repo("ALL")
    assert r is not None and r.fleet is True


# ── FAIL-CLOSED: unknown repo -> ZERO tasks ─────────────────────

def test_pending_fail_closed_returns_empty_and_does_not_query(tmp_path, monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    monkeypatch.chdir(tmp_path)
    with patch.object(task_db, "psql") as mock_psql:
        out, _err, exc = _run_capture(task_db.cmd_pending)
    assert exc is None
    assert json.loads(out) == []
    mock_psql.assert_not_called()


def test_list_fail_closed_returns_no_rows(tmp_path, monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    monkeypatch.chdir(tmp_path)
    with patch.object(task_db, "psql") as mock_psql:
        out, _err, exc = _run_capture(
            task_db.cmd_list, None, None, None, None, None, None, None, None)
    assert exc is None
    assert "No tasks found." in out
    mock_psql.assert_not_called()


def test_board_fail_closed_reports_unknown_repo(tmp_path, monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    monkeypatch.chdir(tmp_path)
    with patch.object(task_db, "psql") as mock_psql:
        out, _err, exc = _run_capture(task_db.cmd_list_board)
    assert exc is None
    assert "unknown" in out.lower()
    mock_psql.assert_not_called()


# ── scoped SQL: strict by default, untagged is opt-in ──────────

def test_pending_scoped_sql_binds_repo_and_excludes_null():
    """DEFAULT: the caller's own repo ONLY. Untagged rows are opt-in."""
    with patch.object(task_db, "psql", return_value=_row_line()) as mock_psql:
        out, _err, exc = _run_capture(task_db.cmd_pending, "steadfaste")
    assert exc is None
    assert json.loads(out)[0]["id"] == "uuid1"
    sql, params = mock_psql.call_args[0][0], mock_psql.call_args[0][1]
    assert "t.repo = " in sql
    assert "t.repo IS NULL" not in sql, \
        "the default scope must not include untagged rows (reported 'too broad')"
    assert params == ["steadfaste", "steadfaste"]


def test_pending_include_untagged_is_opt_in():
    with patch.object(task_db, "psql", return_value=_row_line()) as mock_psql:
        out, _err, exc = _run_capture(task_db.cmd_pending, "steadfaste",
                                      None, None, False, True)
    assert exc is None
    sql, params = mock_psql.call_args[0][0], mock_psql.call_args[0][1]
    assert "t.repo IS NULL" in sql
    assert params == ["steadfaste", "steadfaste"]


def test_list_scoped_sql_excludes_null_repo_by_default():
    with patch.object(task_db, "psql", return_value=_row_line()) as mock_psql:
        _out, _err, exc = _run_capture(
            task_db.cmd_list, None, None, None, None, "steadfaste", None, None, None)
    assert exc is None
    sql, params = mock_psql.call_args[0][0], mock_psql.call_args[0][1]
    assert "t.repo IS NULL" not in sql
    assert params[8:10] == ["steadfaste", "steadfaste"]


def test_list_scoped_sql_includes_null_repo_when_asked():
    with patch.object(task_db, "psql", return_value=_row_line()) as mock_psql:
        _out, _err, exc = _run_capture(
            task_db.cmd_list, None, None, None, None, "steadfaste", None, None, None,
            None, None, None, True)
    assert exc is None
    sql = mock_psql.call_args[0][0]
    assert "t.repo IS NULL" in sql
    assert "t.repo = " in sql


def test_board_scoped_sql_excludes_null_repo_by_default():
    with patch.object(task_db, "schema_version", return_value=9), \
         patch.object(task_db, "psql", return_value="") as mock_psql:
        _out, _err, exc = _run_capture(task_db.cmd_list_board, "steadfaste")
    assert exc is None
    for call in mock_psql.call_args_list:
        sql = call[0][0] if call[0] else ""
        if "tasks.tasks" in sql and "repo" in sql:
            assert "t.repo IS NULL" not in sql, sql
    assert any("steadfaste" in (c[0][1] if len(c[0]) > 1 else [])
               or "steadfaste" in str(c[0]) for c in mock_psql.call_args_list), \
        "board queries must carry the repo filter"


def test_board_include_untagged_is_opt_in():
    with patch.object(task_db, "schema_version", return_value=9), \
         patch.object(task_db, "psql", return_value="") as mock_psql:
        _out, _err, exc = _run_capture(task_db.cmd_list_board, "steadfaste",
                                      None, None, True)
    assert exc is None
    joined = " ".join(str(c[0]) for c in mock_psql.call_args_list)
    assert "t.repo IS NULL" in joined


def test_claimable_and_assigned_are_scoped():
    for fn in (task_db.cmd_list_claimable, task_db.cmd_list_assigned):
        with patch.object(task_db, "schema_version", return_value=9), \
             patch.object(task_db, "psql", return_value="") as mock_psql:
            _out, _err, exc = _run_capture(fn, 10, "steadfaste")
        assert exc is None
        joined = " ".join(str(c[0]) for c in mock_psql.call_args_list)
        assert "steadfaste" in joined, fn.__name__
        assert "t.repo IS NULL" not in joined, fn.__name__


# ── mint path: a new row inherits the session repo ──────────────

def _add_capture(repo_arg, tmp_path, monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    root = _git_init(tmp_path / "project-mint")
    monkeypatch.chdir(root)
    with patch.object(task_db, "psql", return_value="") as mock_psql:
        _out, _err, exc = _run_capture(
            task_db.cmd_add, "content", None, 0, None, repo_arg, None, None,
            None, None, [], None, None, None, True, None)
    assert exc is None
    return mock_psql.call_args[0][1]


def test_add_defaults_repo_to_the_session_repo(tmp_path, monkeypatch):
    params = _add_capture(None, tmp_path, monkeypatch)
    assert params[5] == "project-mint", \
        "a row minted inside a repo must not be untagged (strict default would hide it)"


def test_add_explicit_repo_wins(tmp_path, monkeypatch):
    params = _add_capture("explicit-repo", tmp_path, monkeypatch)
    assert params[5] == "explicit-repo"


def test_add_without_a_resolvable_repo_stays_untagged(tmp_path, monkeypatch):
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    monkeypatch.chdir(tmp_path)  # not a git repo
    with patch.object(task_db, "psql", return_value="") as mock_psql:
        _out, _err, exc = _run_capture(
            task_db.cmd_add, "content", None, 0, None, None, None, None,
            None, None, [], None, None, None, True, None)
    assert exc is None
    assert mock_psql.call_args[0][1][5] is None


def test_fail_closed_costs_no_db_contact_even_for_v4_views(tmp_path, monkeypatch):
    """The fail-closed path must not touch the schema probe either: an unknown
    repo returns nothing regardless of what the database holds."""
    monkeypatch.delenv("CORTEX_SESSION_REPO", raising=False)
    monkeypatch.chdir(tmp_path)
    for fn in (task_db.cmd_list_board, task_db.cmd_list_claimable,
               task_db.cmd_list_assigned):
        with patch.object(task_db, "psql") as mock_psql:
            _out, _err, exc = _run_capture(fn)
        assert exc is None, fn.__name__
        mock_psql.assert_not_called()


def test_pending_repo_all_is_unfiltered():
    """`repo="ALL"` is the ONLY way to ask for every repo — explicit, never default.

    The fleet view is the WIDER of the two: it is unfiltered, so untagged rows
    are included there by construction (no `OR t.repo IS NULL` clause needed).
    """
    with patch.object(task_db, "psql", return_value=_row_line()) as mock_psql:
        _out, _err, exc = _run_capture(task_db.cmd_pending, "ALL")
    assert exc is None
    sql, params = mock_psql.call_args[0][0], mock_psql.call_args[0][1]
    assert "t.repo IS NULL" not in sql, "fleet view must not be repo-scoped"
    assert params is None or all(p is None for p in params)


# ── MCP surface: schema + pass-through ──────────────────────────

SCOPED_TOOLS = ("task_pending", "task_list", "task_board",
                "task_list_claimable", "task_list_handed_out")


def _mcp():
    try:
        import mcp  # noqa: F401
    except ImportError:  # pragma: no cover — mcp absent in this interpreter
        return None
    return _load("task_mcp_scope", TASK_MCP_PATH)


def _schema(tool):
    """mcp.types.Tool exposes `input_schema`; older/newer SDKs alias it."""
    for attr in ("input_schema", "inputSchema"):
        schema = getattr(tool, attr, None)
        if schema is not None:
            return schema
    return {}


def test_scoped_tools_expose_repo_parameter():
    tm = _mcp()
    if tm is None:
        return
    import asyncio
    tools = {t.name: t for t in asyncio.run(tm.list_tools(None)).tools}
    for name in SCOPED_TOOLS:
        schema = _schema(tools[name])
        props = schema.get("properties", {})
        assert "repo" in props, f"{name} has no repo parameter"
        assert "repo" not in schema.get("required", []), name


def test_scoped_tools_expose_the_untagged_switch():
    """The broad view (own repo + untagged) must be reachable from MCP, not only
    from the CLI: without it the worker pool for untagged fleet slices is gone."""
    tm = _mcp()
    if tm is None:
        return
    import asyncio
    tools = {t.name: t for t in asyncio.run(tm.list_tools(None)).tools}
    for name in SCOPED_TOOLS:
        props = _schema(tools[name]).get("properties", {})
        assert "include_untagged" in props, f"{name} has no include_untagged switch"
        assert props["include_untagged"].get("type") == "boolean", name


def test_mcp_forwards_include_untagged_to_the_engine(monkeypatch):
    tm = _mcp()
    if tm is None:
        return
    seen = {}

    def fake_pending(*a, **kw):
        seen["args"], seen["kw"] = a, kw

    monkeypatch.setattr(tm.task_db, "cmd_pending", fake_pending)
    tm._task_pending({"repo": "steadfaste", "include_untagged": True})
    assert seen["kw"].get("include_untagged") is True, \
        "include_untagged must reach cmd_pending"

    seen.clear()

    def fake_list(*a, **kw):
        seen["args"], seen["kw"] = a, kw

    monkeypatch.setattr(tm.task_db, "cmd_list", fake_list)
    tm._task_list({"repo": "steadfaste", "include_untagged": True})
    assert seen["kw"].get("include_untagged") is True, \
        "include_untagged must reach cmd_list"


def test_scoped_tool_descriptions_state_the_contract():
    tm = _mcp()
    if tm is None:
        return
    import asyncio
    tools = {t.name: t for t in asyncio.run(tm.list_tools(None)).tools}
    for name in SCOPED_TOOLS:
        desc = tools[name].description.lower()
        assert "repo" in desc, name


def test_mcp_forwards_repo_and_injected_identity(monkeypatch):
    tm = _mcp()
    if tm is None:
        return
    seen = {}

    def fake_pending(*a, **kw):
        seen["args"] = a
        seen["kw"] = kw

    monkeypatch.setattr(tm.task_db, "cmd_pending", fake_pending)
    tm._task_pending({"repo": "steadfaste", "repo_path": "/tmp/x",
                      "repo_slug": "steadfaste"})
    assert seen["args"][0] == "steadfaste"
    assert seen["args"][1] == "/tmp/x"
    assert seen["args"][2] == "steadfaste"
    assert seen["kw"].get("explain") is False, \
        "stderr must not be merged into the JSON payload"


def test_mcp_board_passes_repo(monkeypatch):
    tm = _mcp()
    if tm is None:
        return
    seen = {}
    monkeypatch.setattr(tm.task_db, "cmd_list_board",
                        lambda *a, **kw: seen.update(args=a, kw=kw))
    tm._task_board({"repo": "steadfaste"})
    assert seen["args"][0] == "steadfaste"
