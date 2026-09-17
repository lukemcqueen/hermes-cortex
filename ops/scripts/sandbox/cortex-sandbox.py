#!/usr/bin/env python3.12
"""
Cortex Sandbox — disk access control for Hermes Cortex agents.

Config file: ~/.hermes-cortex/config.yaml
    folder_access:
      level: full              # "full" (default) or "specific"
      allowed_paths:           # required when level=specific
        - ~/projects
        - ~/work

Module interface:
    load_config() -> SandboxConfig
    Sandbox(config).check(path, operation)  # raises SandboxBlocked if denied
    Sandbox(config).is_allowed(path, op)    # returns bool

CLI:
    python3 cortex-sandbox.py status         # json status
    python3 cortex-sandbox.py check <path>   # exit 0=allowed, 1=blocked
"""

import sys
from pathlib import Path
from typing import Optional, Sequence

import yaml

CONFIG_PATH = Path.home() / ".hermes-cortex" / "config.yaml"
DEFAULT_LEVEL = "full"
VALID_LEVELS = {"full", "specific"}
VALID_OPERATIONS = {"read", "write", "execute", "delete"}


# ── Exceptions ─────────────────────────────────────────────────

class SandboxError(Exception):
    """Base for sandbox errors."""


class SandboxBlocked(SandboxError):
    """Operation blocked by sandbox policy."""

    def __init__(self, path: str, operation: str, allowed_paths: Sequence[Path]):
        self.path = path
        self.operation = operation
        self.allowed_paths = list(allowed_paths)
        joined = ", ".join(str(p) for p in self.allowed_paths)
        super().__init__(
            f"Sandbox blocked {operation} on '{path}': "
            f"only paths under {joined} are permitted."
        )


class SandboxConfigError(SandboxError):
    """Configuration error."""


# ── Config ─────────────────────────────────────────────────────

class SandboxConfig:
    """Parsed sandbox policy. Immutable after construction."""

    def __init__(self, level: str = DEFAULT_LEVEL, allowed_paths: Optional[Sequence[str]] = None):
        if level not in VALID_LEVELS:
            raise SandboxConfigError(
                f"Invalid level '{level}'; must be one of {sorted(VALID_LEVELS)}"
            )
        self.level = level
        self.allowed_paths: tuple[Path, ...] = ()
        if allowed_paths:
            self.allowed_paths = tuple(
                Path(p).expanduser().resolve() for p in allowed_paths
            )

        if self.level == "specific" and not self.allowed_paths:
            raise SandboxConfigError(
                "level=specific requires at least one entry in allowed_paths"
            )

    @property
    def is_restricted(self) -> bool:
        """True when sandbox enforcement is active."""
        return self.level == "specific"

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "allowed_paths": [str(p) for p in self.allowed_paths] or None,
            "is_restricted": self.is_restricted,
        }


def load_config(config_path: Optional[Path] = None) -> SandboxConfig:
    """Load sandbox config from ~/.hermes-cortex/config.yaml.

    Returns default (full access) when file or key is absent.
    Logs warnings to stderr on invalid config and falls back to defaults.
    """
    path = config_path or CONFIG_PATH
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except (FileNotFoundError, OSError):
        return SandboxConfig()
    except yaml.YAMLError as e:
        print(f"cortex-sandbox: invalid YAML in {path}: {e}", file=sys.stderr)
        return SandboxConfig()

    if not isinstance(raw, dict):
        return SandboxConfig()

    sandbox_cfg = raw.get("folder_access")
    if sandbox_cfg is None:
        return SandboxConfig()
    if not isinstance(sandbox_cfg, dict):
        print("cortex-sandbox: 'folder_access' must be a mapping, using defaults", file=sys.stderr)
        return SandboxConfig()

    level = sandbox_cfg.get("level", DEFAULT_LEVEL)
    allowed_paths = sandbox_cfg.get("allowed_paths")

    # Backward compat: accept singular allowed_path as a single-element list.
    if allowed_paths is None and sandbox_cfg.get("allowed_path"):
        allowed_paths = [sandbox_cfg["allowed_path"]]

    if level not in VALID_LEVELS:
        print(f"cortex-sandbox: invalid level '{level}', defaulting to 'full'", file=sys.stderr)
        level = DEFAULT_LEVEL

    if level == "specific" and not allowed_paths:
        print("cortex-sandbox: level=specific but no allowed_paths set, defaulting to 'full'",
              file=sys.stderr)
        level = DEFAULT_LEVEL

    return SandboxConfig(level=level, allowed_paths=allowed_paths)


# ── Sandbox ────────────────────────────────────────────────────

class Sandbox:
    """Validates filesystem paths against a sandbox policy.

    Usage:
        config = load_config()
        sandbox = Sandbox(config)
        sandbox.check("/some/path", "write")  # raises SandboxBlocked if denied
    """

    def __init__(self, config: SandboxConfig):
        self._config = config

    @property
    def config(self) -> SandboxConfig:
        return self._config

    def check(self, path: str | Path, operation: str = "write") -> None:
        """Raise SandboxBlocked if the operation on path is not permitted.

        When level=full, all paths pass.
        When level=specific, only paths under any allowed_path (recursively) pass.
        """
        if not self._config.is_restricted:
            return

        if operation not in VALID_OPERATIONS:
            raise SandboxError(f"Unknown operation: '{operation}'")

        resolved = Path(path).expanduser().resolve()

        for allowed in self._config.allowed_paths:
            try:
                resolved.relative_to(allowed)
                return  # allowed — under one of the permitted trees
            except ValueError:
                continue

        raise SandboxBlocked(str(path), operation, self._config.allowed_paths)

    def is_allowed(self, path: str | Path, operation: str = "write") -> bool:
        """Return True if the operation is permitted."""
        try:
            self.check(path, operation)
            return True
        except SandboxBlocked:
            return False


# ── CLI ────────────────────────────────────────────────────────

def _cmd_status():
    import json
    config = load_config()
    print(json.dumps(config.to_dict(), indent=2))


def _cmd_check():
    if len(sys.argv) < 3:
        print("Usage: cortex-sandbox.py check <path> [operation]", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[2]
    operation = sys.argv[3] if len(sys.argv) > 3 else "write"
    config = load_config()
    sandbox = Sandbox(config)
    try:
        sandbox.check(path, operation)
        print(f"ALLOWED: {operation} '{path}'")
        sys.exit(0)
    except SandboxBlocked as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: cortex-sandbox.py <status|check> [...]", file=sys.stderr)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "status":
        _cmd_status()
    elif cmd == "check":
        _cmd_check()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
