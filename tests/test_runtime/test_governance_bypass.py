"""
Governance Bypass Test Suite — Tests for the governance enforcer plugin.

Tests every code path in plugins/governance-enforcer/__init__.py:

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
_ENFORCER_PATH = Path(__file__).resolve().parents[2] / "plugins" / "governance-enforcer" / "__init__.py"
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
_check_skills_loaded_marker = enforcer._check_skills_loaded_marker
_auto_create_skills_marker = enforcer._auto_create_skills_marker
_session_marker_path = enforcer._session_marker_path
_read_skills_state = enforcer._read_skills_state
_write_skills_state = enforcer._write_skills_state
_get_loaded_skills_summary = enforcer._get_loaded_skills_summary


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


# ═════════════════════════════════════════════════════════════════════════════
# SKILLS-LOADED MARKER — per-session files (multi-session race fix, 2026-08-01)
# ═════════════════════════════════════════════════════════════════════════════
# Regression: the old design used ONE shared ~/.hermes-cortex/state/.skills-loaded
# file. Concurrent sessions (telegram + cli 1 + cli 2 on one server) each loaded
# skills and overwrote that single file with their own session ID, blocking the
# other sessions' write tools mid-task. Per-session marker files
# (state/skills-loaded/<session_id>) make the race structurally impossible.


class TestSkillsMarkerPerSession:
    """Per-session skills-loaded markers — concurrent sessions can't stomp each other."""

    def test_session_creates_own_marker(self, temp_state_dir):
        _auto_create_skills_marker("session_A")
        assert _check_skills_loaded_marker("session_A") is True

    def test_second_session_does_not_invalidate_first(self, temp_state_dir):
        """THE multi-session race: B loading skills must not block A."""
        _auto_create_skills_marker("session_A")
        _auto_create_skills_marker("session_B")   # B loads skills concurrently
        # Old shared-file code: B's write overwrote the single marker, so A's
        # check saw 'session:B' ≠ 'session:A' → blocked. Per-session files: both pass.
        assert _check_skills_loaded_marker("session_A") is True
        assert _check_skills_loaded_marker("session_B") is True

    def test_three_sessions_telegram_cli_cli(self, temp_state_dir):
        """Titus-style: telegram + cli 1 + cli 2 on one server."""
        for sid in ("20260731_telegram_aaa111", "20260731_cli1_bbb222", "20260731_cli2_ccc333"):
            _auto_create_skills_marker(sid)
        for sid in ("20260731_telegram_aaa111", "20260731_cli1_bbb222", "20260731_cli2_ccc333"):
            assert _check_skills_loaded_marker(sid) is True, f"{sid} was stomped"

    def test_touch_bypass_closed(self, temp_state_dir):
        path = _session_marker_path("session_X")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")          # bare `touch`
        assert _check_skills_loaded_marker("session_X") is False

    def test_whitespace_marker_rejected(self, temp_state_dir):
        path = _session_marker_path("session_X")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("   \n")
        assert _check_skills_loaded_marker("session_X") is False

    def test_wrong_session_content_rejected(self, temp_state_dir):
        path = _session_marker_path("session_X")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("session:someone_else")
        assert _check_skills_loaded_marker("session_X") is False

    def test_missing_marker_rejected(self, temp_state_dir):
        assert _check_skills_loaded_marker("ghost_session") is False

    def test_no_session_id_accepts_any_valid_marker(self, temp_state_dir):
        _auto_create_skills_marker("session_A")
        assert _check_skills_loaded_marker("") is True

    def test_no_session_id_no_markers_rejected(self, temp_state_dir):
        assert _check_skills_loaded_marker("") is False

    def test_cron_session_owns_its_marker(self, temp_state_dir):
        """Cron bootstrap creates the cron session's OWN marker without
        touching an interactive session's proof."""
        _auto_create_skills_marker("20260731_interactive_zzz")
        _auto_create_skills_marker("cron_b33bc9b07c55_20260731")
        assert _check_skills_loaded_marker("cron_b33bc9b07c55_20260731") is True
        assert _check_skills_loaded_marker("20260731_interactive_zzz") is True

    def test_legacy_single_file_marker_is_inert(self, temp_state_dir):
        """Old .skills-loaded global file must NOT gate anything anymore."""
        (temp_state_dir / ".skills-loaded").write_text("session:old_legacy")
        assert _check_skills_loaded_marker("old_legacy") is False
        assert _check_skills_loaded_marker("20260731_fresh_abc") is False

    def test_path_traversal_session_id_rejected(self, temp_state_dir):
        """A hostile session ID must never escape the marker dir (../evil)."""
        # create with a traversal id → must not write outside the dir
        _auto_create_skills_marker("../evil")
        assert (temp_state_dir / "evil").exists() is False, "traversal wrote outside!"
        # check with traversal id → graceful False, no crash
        assert _check_skills_loaded_marker("../evil") is False
        assert _check_skills_loaded_marker("a/b") is False
        assert _check_skills_loaded_marker("..") is False

    def test_slash_session_id_does_not_write_nested(self, temp_state_dir):
        _auto_create_skills_marker("sess/with/slash")
        assert (temp_state_dir / "skills-loaded" / "sess").exists() is False


class TestSkillsStatePerSession:
    """Per-session skills-state files — no cross-session bleed."""

    def test_state_is_isolated_per_session(self, temp_state_dir):
        _write_skills_state("sess_A", always_loaded={"task-start"})
        _write_skills_state("sess_B", always_loaded={"agent-flow"})
        assert set(_read_skills_state("sess_A")["always_skills"]) == {"task-start"}
        assert set(_read_skills_state("sess_B")["always_skills"]) == {"agent-flow"}
        assert "task-start" not in _read_skills_state("sess_B")["always_skills"]

    def test_physical_files_are_distinct(self, temp_state_dir):
        _write_skills_state("sess_A", always_loaded={"task-start"})
        _write_skills_state("sess_B", always_loaded={"agent-flow"})
        files = sorted(p.name for p in (temp_state_dir / "skills-state").iterdir())
        assert files == ["sess_A.json", "sess_B.json"]

    def test_summary_is_per_session(self, temp_state_dir):
        _write_skills_state("sess_A", always_loaded={"task-start", "agent-flow"})
        _write_skills_state("sess_B", always_loaded={"change-checklist"})
        assert _get_loaded_skills_summary("sess_A")["task-start"] is True
        assert _get_loaded_skills_summary("sess_A")["change-checklist"] is False
        assert _get_loaded_skills_summary("sess_B")["change-checklist"] is True

    def test_same_session_merge_appends(self, temp_state_dir):
        _write_skills_state("sess_A", always_loaded={"task-start"})
        _write_skills_state("sess_A", always_loaded={"agent-flow"})
        assert set(_read_skills_state("sess_A")["always_skills"]) == {"task-start", "agent-flow"}

    def test_missing_state_returns_empty(self, temp_state_dir):
        assert _read_skills_state("nobody") == {}

    def test_corrupt_state_json_returns_empty(self, temp_state_dir):
        """Corrupt/unparseable state file must not crash the enforcer."""
        state_dir = temp_state_dir / "skills-state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "sess_X.json").write_text("{ not valid json !!!")
        assert _read_skills_state("sess_X") == {}

    def test_unsafe_session_id_state_graceful(self, temp_state_dir):
        """Traversal session IDs fail gracefully in state read/write."""
        _write_skills_state("../evil", always_loaded={"task-start"})
        assert (temp_state_dir / "evil.json").exists() is False
        assert _read_skills_state("../evil") == {}


# ═════════════════════════════════════════════════════════════════════════════
# ADVERSARIAL COMMIT GATE — mandatory verification (2026-08-04 hardening)
# ═════════════════════════════════════════════════════════════════════════════


class TestAdversarialCommitGate:
    """Tests for _check_adversarial_commit_gate — the mandatory adversarial
    verification gate on git commit/push of critical-path changes.

    Hardened 2026-08-04 (Luke directive): first occurrence is a HARD BLOCK
    (no more "💡 SUGGESTION" first-hit education), and the critical path list
    covers ALL ops/scripts/, plugins/, skills/, hooks/, mcp-servers/.
    """

    def _run_gate(self, command: str, staged_files, session_id="sess-adv-test"):
        """Run the gate with a mocked git subprocess returning staged_files."""
        class _FakeResult:
            def __init__(self, stdout):
                self.returncode = 0
                self.stdout = stdout

        def _fake_run(cmd, **kwargs):
            return _FakeResult("\n".join(staged_files) + "\n")

        original_run = enforcer.subprocess.run
        enforcer.subprocess.run = _fake_run
        try:
            return enforcer._check_adversarial_commit_gate(
                "terminal", {"command": command}, session_id,
            )
        finally:
            enforcer.subprocess.run = original_run

    @pytest.fixture(autouse=True)
    def _clean_state(self):
        """Isolate the module-global warnings counter and skills set per test."""
        saved_warnings = dict(enforcer._adversarial_warnings)
        saved_skills = set(enforcer._skills_loaded_in_session)
        enforcer._adversarial_warnings.clear()
        enforcer._skills_loaded_in_session.clear()
        yield
        enforcer._adversarial_warnings.clear()
        enforcer._adversarial_warnings.update(saved_warnings)
        enforcer._skills_loaded_in_session.clear()
        enforcer._skills_loaded_in_session.update(saved_skills)

    # ── First occurrence = HARD BLOCK (no suggestion) ─────────────────────

    def test_first_occurrence_blocks_scripts_change(self):
        """First hit on ops/scripts/ change blocks with REQUIRED (not SUGGESTION)."""
        result = self._run_gate(
            "git commit -m 'update script'",
            ["ops/scripts/some-script.sh"],
        )
        assert result is not None
        assert result["action"] == "block"
        assert "ADVERSARIAL VERIFICATION REQUIRED" in result["message"]
        assert "SUGGESTION" not in result["message"]

    def test_first_occurrence_blocks_enforcer_change(self):
        result = self._run_gate(
            "git commit -m 'enforcer update'",
            ["plugins/governance-enforcer/__init__.py"],
        )
        assert result is not None
        assert result["action"] == "block"

    def test_first_occurrence_blocks_skill_change(self):
        result = self._run_gate(
            "git commit -m 'skill update'",
            ["skills/software-development/change-checklist/SKILL.md"],
        )
        assert result is not None
        assert result["action"] == "block"

    def test_first_occurrence_blocks_hook_change(self):
        result = self._run_gate(
            "git commit -m 'hook update'",
            ["hooks/pre-commit"],
        )
        assert result is not None
        assert result["action"] == "block"

    # ── Skill loaded → passes ─────────────────────────────────────────────

    def test_passes_when_skill_loaded(self):
        enforcer._skills_loaded_in_session.add("adversarial-verifier")
        result = self._run_gate(
            "git commit -m 'update script'",
            ["ops/scripts/some-script.sh"],
        )
        assert result is None

    # ── Non-critical paths → passes ───────────────────────────────────────

    def test_passes_for_non_critical_paths(self):
        result = self._run_gate(
            "git commit -m 'docs update'",
            ["docs/some-guide.md"],
        )
        assert result is None

    # ── Repeat occurrences still block with escalation count ──────────────

    def test_repeat_occurrence_mentions_count(self):
        self._run_gate("git commit -m 'x'", ["ops/scripts/a.sh"])
        result = self._run_gate("git commit -m 'y'", ["ops/scripts/b.sh"])
        assert result is not None
        assert result["action"] == "block"
        assert "time(s)" in result["message"]

    # ── Non-terminal tools pass through ───────────────────────────────────

    def test_non_terminal_tool_passes(self):
        result = enforcer._check_adversarial_commit_gate(
            "write_file", {"path": "/tmp/x"}, "sess-adv-test",
        )
        assert result is None

    # ── Non-commit commands pass through ──────────────────────────────────

    def test_non_commit_command_passes(self):
        result = self._run_gate("ls -la", ["ops/scripts/a.sh"])
        assert result is None
