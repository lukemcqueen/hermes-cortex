"""
Tests for cortex-sandbox.py — folder_access sandbox module.

Verifies: default config, specific config (single + multiple paths), path
blocking, subfolder traversal, invalid config rejection, is_allowed, and
config file loading.
"""

import importlib.machinery
import importlib.util
import tempfile
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent.parent / "ops" / "scripts" / "sandbox" / "cortex-sandbox.py"
_loader = importlib.machinery.SourceFileLoader("cortex_sandbox", str(_MODULE_PATH))
_spec = importlib.util.spec_from_loader("cortex_sandbox", _loader)
cs = importlib.util.module_from_spec(_spec)
_loader.exec_module(cs)


class TestDefaultConfig:
    """When no config is set, level=full — all paths allowed."""

    def test_default_is_full(self):
        config = cs.SandboxConfig()
        assert config.level == "full"
        assert not config.is_restricted
        assert config.allowed_paths == ()

    def test_full_allows_any_path(self):
        sandbox = cs.Sandbox(cs.SandboxConfig())
        sandbox.check("/etc/passwd", "read")
        sandbox.check("/tmp/anything", "write")
        sandbox.check("/var/log/syslog", "read")

    def test_full_is_allowed_returns_true(self):
        sandbox = cs.Sandbox(cs.SandboxConfig())
        assert sandbox.is_allowed("/etc/shadow", "read")
        assert sandbox.is_allowed("/root/secret", "write")


class TestSpecificConfig:
    """When level=specific, only paths under an allowed_path are permitted."""

    def test_specific_is_restricted(self):
        config = cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"])
        assert config.is_restricted
        assert config.allowed_paths == (Path("/tmp/test-area"),)

    def test_allowed_path_passes(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        sandbox.check("/tmp/test-area/file.txt", "write")
        sandbox.check("/tmp/test-area/deep/nested/file.py", "write")

    def test_allowed_root_itself_passes(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        sandbox.check("/tmp/test-area", "write")

    def test_path_outside_blocked(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        try:
            sandbox.check("/etc/passwd", "write")
            assert False, "Should have raised SandboxBlocked"
        except cs.SandboxBlocked as e:
            assert "blocked" in str(e).lower()
            assert "/etc/passwd" in str(e)
            assert "/tmp/test-area" in str(e)

    def test_sibling_dir_blocked(self):
        """A path that shares a prefix but isn't under the allowed tree must be blocked."""
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        try:
            sandbox.check("/tmp/test-area-other/file.txt", "write")
            assert False, "Should have raised SandboxBlocked"
        except cs.SandboxBlocked:
            pass

    def test_is_allowed_returns_correct_bools(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        assert sandbox.is_allowed("/tmp/test-area/file", "write")
        assert not sandbox.is_allowed("/etc/shadow", "write")


class TestMultiplePaths:
    """level=specific with multiple allowed paths — any one matches."""

    def test_each_path_allowed(self):
        config = cs.SandboxConfig(
            level="specific",
            allowed_paths=["/tmp/area-a", "/tmp/area-b"],
        )
        sandbox = cs.Sandbox(config)
        sandbox.check("/tmp/area-a/file.txt", "write")
        sandbox.check("/tmp/area-b/other.txt", "write")

    def test_path_outside_all_blocked(self):
        sandbox = cs.Sandbox(
            cs.SandboxConfig(level="specific", allowed_paths=["/tmp/area-a", "/tmp/area-b"])
        )
        try:
            sandbox.check("/tmp/area-c/file.txt", "write")
            assert False, "Should have raised SandboxBlocked"
        except cs.SandboxBlocked as e:
            assert "/tmp/area-a" in str(e)
            assert "/tmp/area-b" in str(e)

    def test_to_dict_lists_all(self):
        config = cs.SandboxConfig(level="specific", allowed_paths=["/tmp/area-a", "/tmp/area-b"])
        d = config.to_dict()
        assert d["allowed_paths"] == ["/tmp/area-a", "/tmp/area-b"]


class TestReadOpen:
    """Under level=specific, reads are unrestricted; mutations are gated."""

    def test_read_outside_allowed(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        sandbox.check("/etc/passwd", "read")
        sandbox.check(str(Path.home() / "other" / "file.txt"), "read")

    def test_is_allowed_read_outside_true(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        assert sandbox.is_allowed("/etc/shadow", "read")

    def test_mutations_outside_still_blocked(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        for op in ("write", "execute", "delete"):
            assert not sandbox.is_allowed("/etc/passwd", op)


class TestTildeExpansion:
    """allowed_paths entries with ~ expand to the user's home directory."""

    def test_tilde_expands(self):
        config = cs.SandboxConfig(level="specific", allowed_paths=["~/projects"])
        assert config.allowed_paths == (Path.home() / "projects",)


class TestInvalidConfig:
    """Invalid config values are rejected at construction time."""

    def test_invalid_level_rejected(self):
        try:
            cs.SandboxConfig(level="nonexistent")
            assert False, "Should have raised SandboxConfigError"
        except cs.SandboxConfigError:
            pass

    def test_specific_without_path_rejected(self):
        try:
            cs.SandboxConfig(level="specific")
            assert False, "Should have raised SandboxConfigError"
        except cs.SandboxConfigError:
            pass

    def test_specific_with_empty_list_rejected(self):
        try:
            cs.SandboxConfig(level="specific", allowed_paths=[])
            assert False, "Should have raised SandboxConfigError"
        except cs.SandboxConfigError:
            pass


class TestConfigDict:
    """to_dict() serializes correctly."""

    def test_full_config_dict(self):
        config = cs.SandboxConfig()
        d = config.to_dict()
        assert d["level"] == "full"
        assert d["allowed_paths"] is None
        assert not d["is_restricted"]

    def test_specific_config_dict(self):
        config = cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"])
        d = config.to_dict()
        assert d["level"] == "specific"
        assert d["allowed_paths"] == ["/tmp/test-area"]
        assert d["is_restricted"]


class TestLoadConfigFromFile:
    """load_config() reads YAML from disk."""

    def test_missing_file_defaults_to_full(self):
        config = cs.load_config(Path("/nonexistent/path/config.yaml"))
        assert config.level == "full"
        assert not config.is_restricted

    def test_folder_access_list_read(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("folder_access:\n  level: specific\n  allowed_paths:\n    - /tmp/my-dir\n    - /tmp/other\n")
            f.flush()
            path = Path(f.name)
        try:
            config = cs.load_config(path)
            assert config.level == "specific"
            assert config.allowed_paths == (Path("/tmp/my-dir"), Path("/tmp/other"))
        finally:
            path.unlink()

    def test_backward_compat_singular_allowed_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("folder_access:\n  level: specific\n  allowed_path: /tmp/my-dir\n")
            f.flush()
            path = Path(f.name)
        try:
            config = cs.load_config(path)
            assert config.level == "specific"
            assert config.allowed_paths == (Path("/tmp/my-dir"),)
        finally:
            path.unlink()

    def test_missing_folder_access_defaults_to_full(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("other_key: value\n")
            f.flush()
            path = Path(f.name)
        try:
            config = cs.load_config(path)
            assert config.level == "full"
        finally:
            path.unlink()


class TestAllOperations:
    """All four operation types are supported."""

    def test_all_operations_pass_when_allowed(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        for op in ("read", "write", "execute", "delete"):
            sandbox.check("/tmp/test-area/file", op)

    def test_all_operations_blocked_when_outside(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/test-area"]))
        for op in ("write", "execute", "delete"):
            try:
                sandbox.check("/etc/passwd", op)
                assert False, f"Should have blocked {op}"
            except cs.SandboxBlocked:
                pass

    def test_unknown_operation_raises(self):
        sandbox = cs.Sandbox(cs.SandboxConfig(level="specific", allowed_paths=["/tmp/x"]))
        try:
            sandbox.check("/tmp/x", "unknown_op")
            assert False, "Should have raised SandboxError"
        except cs.SandboxError:
            pass
