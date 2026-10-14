"""Cycle 12593: the enforcer must stamp repo identity onto mcp__tasks__* calls.

WHY: the tasks MCP server is ONE shared child per host, spawned by the gateway
daemon, whose cwd is HOME (measured 2026-10-14: cwd=/home/<user>, no
CORTEX_SESSION_REPO). A repo-scoped task query therefore cannot learn the
SESSION's repo from its own process — the enforcer is the only component that
observed it, and it already injects repo_path/repo_slug into governance calls.

Both directions are asserted, because either one alone is not a contract:
  * mcp__tasks__* and mcp__loop_governance__* carry the repo when it was observed;
  * an unrelated tool namespace stays untouched;
  * a session whose repo was NEVER observed gets NO repo keys (never invented).
"""
import importlib.util
from pathlib import Path

_ENFORCER_PATH = (
    Path(__file__).resolve().parents[2]
    / "plugins" / "governance-enforcer" / "__init__.py"
)
_spec = importlib.util.spec_from_file_location("governance_enforcer_tasks", _ENFORCER_PATH)
assert _spec is not None and _spec.loader is not None
_enforcer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_enforcer)

_SESSION = "sess-repo-injection"
_OBSERVED = Path("/home/example/projects/steadfaste")


def _patch_repo(monkeypatch, observed, legacy=""):
    monkeypatch.setattr(_enforcer, "_session_repo_path", lambda sid: observed)
    monkeypatch.setattr(_enforcer, "_session_repo_hint", lambda sid: legacy)


def test_task_call_gets_injected_repo_identity(monkeypatch):
    _patch_repo(monkeypatch, _OBSERVED)
    args = {}
    _enforcer._inject_session_context(_SESSION, "mcp__tasks__task_pending", args)
    assert args["session_id"] == _SESSION
    assert args["repo_path"] == str(_OBSERVED)
    assert args["repo_slug"] == "steadfaste"


def test_every_scoped_task_tool_is_covered(monkeypatch):
    _patch_repo(monkeypatch, _OBSERVED)
    for tool in ("mcp__tasks__task_pending", "mcp__tasks__task_list",
                 "mcp__tasks__task_board", "mcp__tasks__task_list_claimable",
                 "mcp__tasks__task_list_handed_out"):
        args = {}
        _enforcer._inject_session_context(_SESSION, tool, args)
        assert args.get("repo_slug") == "steadfaste", tool


def test_governance_injection_unchanged(monkeypatch):
    _patch_repo(monkeypatch, _OBSERVED)
    args = {}
    _enforcer._inject_session_context(_SESSION, "mcp__loop_governance__begin_change", args)
    assert args["repo_path"] == str(_OBSERVED) and args["repo_slug"] == "steadfaste"


def test_unrelated_namespace_is_not_stamped_with_a_repo(monkeypatch):
    _patch_repo(monkeypatch, _OBSERVED)
    args = {}
    _enforcer._inject_session_context(_SESSION, "mcp__cortex_bus__inbox_send", args)
    assert args == {"session_id": _SESSION}


def test_unobserved_repo_is_never_invented(monkeypatch):
    """No observed repo and no legacy hint -> the call carries no repo at all,
    so the task engine's own ladder decides (and refuses) instead of being
    handed a guess."""
    _patch_repo(monkeypatch, None, legacy="")
    args = {}
    _enforcer._inject_session_context(_SESSION, "mcp__tasks__task_pending", args)
    assert args == {"session_id": _SESSION}


def test_legacy_slug_hint_travels_when_no_path_was_observed(monkeypatch):
    _patch_repo(monkeypatch, None, legacy="steadfaste")
    args = {}
    _enforcer._inject_session_context(_SESSION, "mcp__tasks__task_pending", args)
    assert args.get("repo_slug") == "steadfaste"
    assert "repo_path" not in args
