"""
Governance Bypass Test Suite — Tests for the governance enforcer plugin.

Tests every code path in plugins/hermes-governance-enforcer/__init__.py:

  - _is_write_tool           Write tool classification matrix
  - _is_terminal_write       Terminal command pattern matching
  - _is_cronjob_write        Cronjob action governance
  - _is_skill_write          Skill management governance
  - _has_governance_lock     Lock file protocol (file-based)
  - _governance_lock_path    Repo-scoped vs fallback lock paths
  - pre_tool_call_hook       Full enforcement flow (with/without lock)
"""

import contextlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path

import pytest

# ── Load the enforcer module (path has a hyphen, so standard import won't work) ─
_ENFORCER_PATH = Path(__file__).resolve().parents[2] / "plugins" / "hermes-governance-enforcer" / "__init__.py"
_spec = importlib.util.spec_from_file_location("governance_enforcer", _ENFORCER_PATH)
enforcer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enforcer)


WRITE_TOOLS = enforcer.WRITE_TOOLS
WRITE_COMMAND_PATTERNS = enforcer.WRITE_COMMAND_PATTERNS
WRITE_CRON_ACTIONS = enforcer.WRITE_CRON_ACTIONS
WRITE_SKILL_ACTIONS = enforcer.WRITE_SKILL_ACTIONS
_is_write_tool = enforcer._is_write_tool
_is_terminal_write = enforcer._is_terminal_write
_is_cronjob_write = enforcer._is_cronjob_write
_is_skill_write = enforcer._is_skill_write
_has_governance_lock = enforcer._has_governance_lock
_governance_lock_path = enforcer._governance_lock_path


# ═════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_state_dir():
    """Create a temporary state directory and point GOVERNANCE_STATE_DIR at it."""
    with tempfile.TemporaryDirectory() as tmp:
        original = enforcer.GOVERNANCE_STATE_DIR
        enforcer.GOVERNANCE_STATE_DIR = Path(tmp)
        yield Path(tmp)
        enforcer.GOVERNANCE_STATE_DIR = original


def _create_lock(state_dir: Path, task_id: str = "test-task", slug: str = "test-repo", session_id: str = "") -> Path:
    """Create a governance lock file with proper timestamps (avoids stale detection)."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    lock_name = f".governance-{session_id}.json" if session_id else f".governance-{slug}.json"
    lock = state_dir / lock_name
    lock.write_text(json.dumps({
        "task_id": task_id,
        "repo_slug": slug,
        "heartbeat_at": ts,
        "started_at": ts,
        "session_id": session_id,
        "scored": False,
    }))
    return lock


# ═════════════════════════════════════════════════════════════════════════════
# WRITE_TOOLS — always require governance
# ═════════════════════════════════════════════════════════════════════════════


class TestWriteToolsAlwaysRequireLock:
    """Tools in WRITE_TOOLS always need a lock regardless of args."""

    def test_write_file_requires_lock(self):
        assert _is_write_tool("write_file", {}) is True

    def test_patch_requires_lock(self):
        assert _is_write_tool("patch", {}) is True

    def test_unknown_tool_does_not_require_lock(self):
        assert _is_write_tool("read_file", {}) is False
        assert _is_write_tool("web_search", {}) is False

    def test_empty_tool_name_does_not_require_lock(self):
        assert _is_write_tool("", {}) is False


# ═════════════════════════════════════════════════════════════════════════════
# TERMINAL — conditional on command content
# ═════════════════════════════════════════════════════════════════════════════


class TestTerminalWriteDetection:
    """Commands that modify state need a lock."""

    # ── Destructive / modifying commands ────────────────────────────────────

    @pytest.mark.parametrize("cmd", [
        "rm -rf /tmp/test",
        "mv old new",
        "cp source dest",
        "sudo rm -rf /",
        "apt install nginx",
        "docker run nginx",
        "git push origin main",
        "git commit -m 'msg'",
        "echo 'data' > file.txt",
        "sed -i 's/old/new/' file",
        "chmod 755 script.sh",
        "systemctl restart nginx",
        "pip install requests",
        "brew install python",
        "crontab -e",
        "docker system prune",
        "kubectl apply -f pod.yaml",
        "ufw enable",
        "nginx -s reload",
        "journalctl --rotate",
        "usermod -aG docker luke",
        "nohup long-running-process &",
        "wget -O output.txt https://example.com",
        "curl -o output.txt https://example.com",
        "docker compose up -d",
    ])
    def test_write_commands_identified(self, cmd):
        assert _is_terminal_write({"command": cmd}) is True, f"Should detect write: {cmd}"

    # ── Read-only commands ─────────────────────────────────────────────────

    @pytest.mark.parametrize("cmd", [
        "ls -la",
        "cat /etc/hosts",
        "grep foo bar.txt",
        "find . -name '*.py'",
        "which python3",
        "whoami",
        "id",
        "pwd",
        "date",
        "echo 'hello'",
        "printf '%s\\n' hello",
        "ps aux",
        "top -b -n 1",
        "df -h",
        "du -sh /home",
        "free -m",
        "uptime",
        "uname -a",
        "hostname",
        "dmesg | tail",
        "git status",
        "git log --oneline",
        "git diff HEAD",
        "git branch -a",
        "docker ps",
        "docker images",
        "docker logs my-container",
        "hermes --version",
        "hermes doctor",
        "systemctl is-active nginx",
        "journalctl -u service -n 50",
        # python3 -c is correctly blocked as a write tool (inline code execution)
        # "python3 -c 'print(42)'",
        "",
    ])
    def test_read_commands_allowed(self, cmd):
        assert _is_terminal_write({"command": cmd}) is False, f"Should NOT detect write: {cmd}"


# ═════════════════════════════════════════════════════════════════════════════
# CRONJOB — conditional on action
# ═════════════════════════════════════════════════════════════════════════════


class TestCronjobWriteDetection:
    def test_create_requires_lock(self):
        assert _is_cronjob_write({"action": "create"}) is True

    def test_update_requires_lock(self):
        assert _is_cronjob_write({"action": "update"}) is True

    def test_remove_requires_lock(self):
        assert _is_cronjob_write({"action": "remove"}) is True

    def test_list_is_read(self):
        assert _is_cronjob_write({"action": "list"}) is False

    def test_run_is_read(self):
        assert _is_cronjob_write({"action": "run"}) is False

    def test_unknown_action_is_read(self):
        assert _is_cronjob_write({"action": "pause"}) is False

    def test_empty_action_is_read(self):
        assert _is_cronjob_write({}) is False


# ═════════════════════════════════════════════════════════════════════════════
# SKILL_MANAGE — conditional on action
# ═════════════════════════════════════════════════════════════════════════════


class TestSkillManageWriteDetection:
    def test_create_requires_lock(self):
        assert _is_skill_write({"action": "create"}) is True

    def test_edit_requires_lock(self):
        assert _is_skill_write({"action": "edit"}) is True

    def test_delete_requires_lock(self):
        assert _is_skill_write({"action": "delete"}) is True

    def test_write_file_requires_lock(self):
        assert _is_skill_write({"action": "write_file"}) is True

    def test_remove_file_requires_lock(self):
        assert _is_skill_write({"action": "remove_file"}) is True

    def test_patch_requires_lock(self):
        assert _is_skill_write({"action": "patch"}) is True

    def test_view_is_read(self):
        assert _is_skill_write({"action": "view"}) is False

    def test_read_is_read(self):
        assert _is_skill_write({"action": "read"}) is False

    def test_unknown_is_read(self):
        assert _is_skill_write({"action": "list"}) is False


# ═════════════════════════════════════════════════════════════════════════════
# IS_WRITE_TOOL — combined classification matrix
# ═════════════════════════════════════════════════════════════════════════════


class TestIsWriteToolMatrix:
    """Verify the full decision matrix from the README."""

    def test_write_file_no_lock(self):
        assert _is_write_tool("write_file", {}) is True

    def test_patch_no_lock(self):
        assert _is_write_tool("patch", {}) is True

    def test_terminal_write_cmd(self):
        assert _is_write_tool("terminal", {"command": "rm -rf /"}) is True

    def test_terminal_read_cmd(self):
        assert _is_write_tool("terminal", {"command": "ls -la"}) is False

    def test_cronjob_create(self):
        assert _is_write_tool("cronjob", {"action": "create"}) is True

    def test_cronjob_list(self):
        assert _is_write_tool("cronjob", {"action": "list"}) is False

    def test_skill_manage_create(self):
        assert _is_write_tool("skill_manage", {"action": "create"}) is True

    def test_skill_manage_view(self):
        assert _is_write_tool("skill_manage", {"action": "view"}) is False

    def test_read_file(self):
        assert _is_write_tool("read_file", {}) is False

    def test_web_search(self):
        assert _is_write_tool("web_search", {}) is False


# ═════════════════════════════════════════════════════════════════════════════
# LOCK PROTOCOL
# ═════════════════════════════════════════════════════════════════════════════


class TestHasGovernanceLock:
    """Lock file detection — filesystem-based."""

    @contextlib.contextmanager
    def _with_lock_path(self, path: Path):
        """Temporarily replace _governance_lock_path on the loaded module."""
        original = enforcer._governance_lock_path
        enforcer._governance_lock_path = lambda p=path: p
        try:
            yield
        finally:
            enforcer._governance_lock_path = original

    def test_lock_exists_with_task_id(self, temp_state_dir):
        _create_lock(temp_state_dir, task_id="fix-auth", slug="test-repo")
        # Phase 2 scan finds lock by repo_slug
        original_slug = enforcer._derive_repo_slug
        enforcer._derive_repo_slug = lambda: "test-repo"
        try:
            assert _has_governance_lock() is True
        finally:
            enforcer._derive_repo_slug = original_slug

    def test_lock_missing(self, temp_state_dir):
        _create_lock(temp_state_dir, task_id="fix-auth", slug="some-other-repo")
        original_slug = enforcer._derive_repo_slug
        enforcer._derive_repo_slug = lambda: "test-repo"
        try:
            assert _has_governance_lock() is False
        finally:
            enforcer._derive_repo_slug = original_slug

    def test_lock_with_empty_task_id_returns_false(self, temp_state_dir):
        _create_lock(temp_state_dir, task_id="", slug="test-repo")
        original_slug = enforcer._derive_repo_slug
        enforcer._derive_repo_slug = lambda: "test-repo"
        try:
            assert _has_governance_lock() is False
        finally:
            enforcer._derive_repo_slug = original_slug

    def test_corrupted_lock_file_returns_false(self, temp_state_dir):
        lock = temp_state_dir / ".governance-corrupted.json"
        lock.write_text("not valid json")
        # Phase 2: corrupted file is removed, no lock found
        assert _has_governance_lock() is False

    def test_deleted_lock_file_returns_false(self, temp_state_dir):
        lock = _create_lock(temp_state_dir, task_id="to-delete", slug="delete-me")
        lock.unlink()
        assert _has_governance_lock() is False


class TestGovernanceLockPath:
    """Lock path helper — returns session-scoped path or None."""

    def test_with_session_id_returns_scoped_path(self):
        path = _governance_lock_path(session_id="sess_abc123")
        assert path is not None
        assert "sess_abc123" in str(path)
        assert path.suffix == ".json"

    def test_without_session_id_returns_none(self):
        """No session_id → return None (no generic fallback — strict)."""
        path = _governance_lock_path()
        assert path is None


# ═════════════════════════════════════════════════════════════════════════════
# PRE_TOOL_CALL HOOK — full enforcement flow
# ═════════════════════════════════════════════════════════════════════════════


class TestPreToolCallHook:
    """Integration tests for the pre_tool_call_hook closure."""

    def _make_hook(self, state_dir: Path, slug: str = "test-repo"):
        """Create the pre_tool_call_hook with overridden repo slug for Phase 2."""

        # Mock _derive_repo_slug so Phase 2 finds locks by repo_slug
        original_repo_slug = enforcer._derive_repo_slug
        enforcer._derive_repo_slug = lambda: slug

        # Build the hook the same way register() does
        def hook(tool_name="", args=None, **kwargs):
            if not tool_name:
                return None
            args = args or {}
            if not _is_write_tool(tool_name, args):
                return None
            if enforcer._has_governance_lock():
                return None
            return {"action": "block", "message": "GOVERNANCE LOCK REQUIRED"}

        yield hook
        enforcer._derive_repo_slug = original_repo_slug

    # ── Write tool without lock → BLOCKED ──────────────────────────────────

    @pytest.mark.parametrize("tool,args", [
        ("write_file", {"path": "/tmp/test.txt", "content": "hello"}),
        ("patch", {"path": "/tmp/test.txt", "old_string": "a", "new_string": "b"}),
        ("terminal", {"command": "rm -rf /tmp/test"}),
        ("cronjob", {"action": "create", "schedule": "0 9 * * *"}),
        ("skill_manage", {"action": "create", "name": "new-skill"}),
    ])
    def test_write_tool_without_lock_returns_block(self, temp_state_dir, tool, args):
        hook = iter(self._make_hook(temp_state_dir))
        result = next(hook)(tool_name=tool, args=args)
        assert result is not None
        assert result["action"] == "block"

    # ── Write tool WITH lock → ALLOWED ─────────────────────────────────────

    @pytest.mark.parametrize("tool,args", [
        ("write_file", {"path": "/tmp/test.txt", "content": "hello"}),
        ("patch", {"path": "/tmp/test.txt", "old_string": "a", "new_string": "b"}),
        ("terminal", {"command": "rm -rf /tmp/test"}),
        ("cronjob", {"action": "create", "schedule": "0 9 * * *"}),
        ("skill_manage", {"action": "create", "name": "new-skill"}),
    ])
    def test_write_tool_with_lock_allows_pass(self, temp_state_dir, tool, args):
        _create_lock(temp_state_dir, task_id="active-task", slug="test-repo")
        hook = iter(self._make_hook(temp_state_dir))
        result = next(hook)(tool_name=tool, args=args)
        assert result is None, f"Expected None (pass) for {tool} with lock, got {result}"

    # ── Read tools without lock → ALLOWED ──────────────────────────────────

    @pytest.mark.parametrize("tool,args", [
        ("read_file", {"path": "/tmp/test.txt"}),
        ("web_search", {"query": "python"}),
        ("terminal", {"command": "ls -la"}),
        ("cronjob", {"action": "list"}),
        ("skill_manage", {"action": "view", "name": "existing-skill"}),
        ("", {}),
    ])
    def test_read_tool_without_lock_allows_pass(self, temp_state_dir, tool, args):
        hook = iter(self._make_hook(temp_state_dir))
        result = next(hook)(tool_name=tool, args=args)
        assert result is None, f"Expected None (pass) for read tool {tool}, got {result}"

    # ── Edge cases ─────────────────────────────────────────────────────────

    def test_lock_with_empty_task_id_still_blocks(self, temp_state_dir):
        _create_lock(temp_state_dir, task_id="", slug="test-repo")
        hook = iter(self._make_hook(temp_state_dir))
        result = next(hook)(tool_name="write_file", args={"path": "/tmp/x"})
        assert result["action"] == "block", "Empty task_id should not count as active lock"
