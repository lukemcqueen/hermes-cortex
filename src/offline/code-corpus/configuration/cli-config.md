---
language: python
tags: [configuration, cli, profiles, credentials]
title: CLI Configuration Patterns
description: Flags vs env vs config file precedence, persistent config in ~/.config/, profile switching, and credential management for CLI tools
source: pattern
---

```python
# === PRECEDENCE: Flags > Env Vars > Config File > Defaults ===
#
# CLI tools should respect a clear precedence hierarchy:
#   1. Command-line flags (highest — explicit user intent)
#   2. Environment variables (for CI/Docker/automation)
#   3. Config file (~/.config/<tool>/config.yaml — persistent user prefs)
#   4. Default values (lowest — hardcoded in code)

import argparse
import os
import yaml
from pathlib import Path
from typing import Any

# === 1. CONFIG FILE LOCATION ===

# XDG Base Directory spec: ~/.config/<tool>/
CONFIG_DIR = Path.home() / ".config" / "mycli"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.yaml"  # 0600 permissions

# Legacy fallback: ~/.<tool>rc
LEGACY_CONFIG = Path.home() / ".myclirc"
```

```python
# === 2. CONFIG LOADING WITH PRECEDENCE ===

class CLIConfig:
    """Load and merge configuration from all sources with proper precedence."""

    def __init__(self, tool_name: str = "mycli"):
        self._tool_name = tool_name
        self._config_dir = Path.home() / ".config" / tool_name
        self._config_file = self._config_dir / "config.yaml"

    def load(self, args: argparse.Namespace | None = None) -> dict[str, Any]:
        """Merge config from all sources. Flags beat env vars beat config file."""
        config: dict[str, Any] = {}

        # Step 1: Defaults
        config.update(self._defaults())

        # Step 2: Config file (persistent user prefs)
        config.update(self._load_config_file())

        # Step 3: Legacy config file (backward compat)
        legacy = Path.home() / f".{self._tool_name}rc"
        if legacy.exists():
            config.update(self._load_legacy(legacy))

        # Step 4: Environment variables
        config.update(self._load_env_vars())

        # Step 5: Command-line flags (highest precedence)
        if args:
            config.update(self._parse_flags(args))

        return config

    def _defaults(self) -> dict:
        return {
            "format": "table",
            "timeout": 30,
            "color": True,
            "verbose": False,
            "profile": "default",
            "output_dir": str(Path.cwd()),
        }

    def _load_config_file(self) -> dict:
        """Load YAML config file with XDG path."""
        if self._config_file.exists():
            with open(self._config_file) as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_legacy(self, path: Path) -> dict:
        """Load legacy ~/.<tool>rc format (INI-like key=value)."""
        config = {}
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, _, value = line.partition("=")
                        config[key.strip()] = value.strip()
        return config

    def _load_env_vars(self) -> dict:
        """Map environment variables to config keys."""
        prefix = f"{self._tool_name.upper()}_"
        mapping = {
            f"{prefix}FORMAT": "format",
            f"{prefix}TIMEOUT": "timeout",
            f"{prefix}COLOR": "color",
            f"{prefix}VERBOSE": "verbose",
            f"{prefix}PROFILE": "profile",
            f"{prefix}OUTPUT_DIR": "output_dir",
            f"{prefix}API_KEY": "api_key",
        }
        config = {}
        for env_var, config_key in mapping.items():
            value = os.environ.get(env_var)
            if value is not None:
                # Type-coerce based on default type
                config[config_key] = self._coerce(value, config_key)
        return config

    def _coerce(self, value: str, key: str) -> Any:
        """Attempt to parse typed values from string env vars."""
        type_map = {
            "timeout": int,
            "color": lambda v: v.lower() in ("1", "true", "yes"),
            "verbose": lambda v: v.lower() in ("1", "true", "yes"),
        }
        converter = type_map.get(key)
        return converter(value) if converter else value

    def _parse_flags(self, args: argparse.Namespace) -> dict:
        """Extract explicitly-set flags (not defaults) from argparse."""
        config = {}
        flag_map = {
            "format": "format",
            "timeout": "timeout",
            "color": "color",
            "verbose": "verbose",
            "profile": "profile",
            "output_dir": "output_dir",
        }
        for flag_name, config_key in flag_map.items():
            value = getattr(args, flag_name, None)
            if value is not None:
                config[config_key] = value
        return config


# === 3. ARGPARSE SETUP ===

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mycli",
        description="MyCLI — a well-configured CLI tool",
        epilog="Config file: ~/.config/mycli/config.yaml",
    )

    # Global flags
    parser.add_argument(
        "--format", "-f",
        choices=["table", "json", "yaml"],
        help="Output format (env: MYCLI_FORMAT)",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        help="Request timeout in seconds (env: MYCLI_TIMEOUT)",
    )
    parser.add_argument(
        "--color",
        action=argparse.BooleanOptionalAction,
        help="Enable/disable color output (env: MYCLI_COLOR)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output (env: MYCLI_VERBOSE)",
    )
    parser.add_argument(
        "--profile", "-p",
        help="Configuration profile to use (env: MYCLI_PROFILE)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="Output directory (env: MYCLI_OUTPUT_DIR)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Deploy subcommand
    deploy_parser = subparsers.add_parser("deploy", help="Deploy resources")
    deploy_parser.add_argument("target", help="Deployment target")
    deploy_parser.add_argument("--dry-run", action="store_true")

    # Config subcommand
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_sub = config_parser.add_subparsers(dest="config_action")
    config_sub.add_parser("show", help="Show current config")
    config_sub.add_parser("edit", help="Open config in editor")
    config_sub.add_parser("init", help="Create default config file")

    return parser
```

```python
# === 4. PROFILE SWITCHING ===

class ProfileManager:
    """Manage multiple named configuration profiles.

    ~/.config/mycli/
      config.yaml           # Active configuration (merged result)
      profiles/
        default.yaml        # Default profile
        production.yaml     # Production-specific profile
        staging.yaml        # Staging-specific profile
      credentials.yaml      # Stored credentials (0600 permissions)
    """

    def __init__(self, tool_name: str = "mycli"):
        self._base = Path.home() / ".config" / tool_name
        self._profiles_dir = self._base / "profiles"

    def list_profiles(self) -> list[str]:
        """List available profiles."""
        if not self._profiles_dir.exists():
            return ["default"]
        return sorted(
            p.stem for p in self._profiles_dir.glob("*.yaml") if p.stem != "credentials"
        )

    def switch_profile(self, profile_name: str) -> bool:
        """Switch active profile by copying profile config to config.yaml."""
        profile_path = self._profiles_dir / f"{profile_name}.yaml"
        if not profile_path.exists():
            print(f"Profile '{profile_name}' not found.")
            return False

        # Copy profile to active config
        config_path = self._base / "config.yaml"
        config_path.write_text(profile_path.read_text())
        print(f"Switched to profile: {profile_name}")
        return True

    def ensure_profile_dir(self) -> Path:
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        return self._profiles_dir


# === 5. CREDENTIAL MANAGEMENT ===

import stat

class CredentialManager:
    """Safely manage stored credentials with correct file permissions."""

    def __init__(self, tool_name: str = "mycli"):
        self._path = Path.home() / ".config" / tool_name / "credentials.yaml"

    def get(self, key: str, default: str | None = None) -> str | None:
        """Retrieve a credential."""
        creds = self._load()
        return creds.get(key, default)

    def set(self, key: str, value: str) -> None:
        """Store a credential. Creates file with 0600 permissions."""
        creds = self._load()
        creds[key] = value
        self._save(creds)

    def delete(self, key: str) -> bool:
        """Remove a credential."""
        creds = self._load()
        if key in creds:
            del creds[key]
            self._save(creds)
            return True
        return False

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def _save(self, creds: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            yaml.dump(creds, f, default_flow_style=False)
        # Set 0600 permissions (owner read/write only)
        self._path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def clear(self) -> None:
        """Wipe all stored credentials."""
        if self._path.exists():
            self._path.unlink()
```

```python
# === 6. FULL CLI ENTRY POINT ===

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Load config with full precedence
    config_loader = CLIConfig(tool_name="mycli")
    config = config_loader.load(args)

    # Initialize credential manager
    creds = CredentialManager("mycli")

    # Handle profile switching
    profile_manager = ProfileManager("mycli")
    profile = config.get("profile", "default")

    if profile != "default" and profile not in profile_manager.list_profiles():
        print(f"Warning: Profile '{profile}' not found. Using 'default'.")
        profile = "default"

    # Dispatch command
    match args.command:
        case "config":
            match args.config_action:
                case "show":
                    import json
                    print(json.dumps(config, indent=2))
                case "edit":
                    editor = os.environ.get("EDITOR", "nano")
                    config_file = CONFIG_DIR / "config.yaml"
                    os.system(f"{editor} {config_file}")
                case "init":
                    _create_default_config()

        case "deploy":
            api_key = creds.get("api_key")
            if not api_key:
                print("Error: No API key configured. Run: mycli config set api-key <key>")
                sys.exit(1)

            print(f"Deploying to {args.target}...")
            print(f"Profile: {profile}")
            print(f"Format: {config['format']}")
            print(f"Timeout: {config['timeout']}s")
            if args.dry_run:
                print("DRY RUN — no changes made")

        case _:
            parser.print_help()


def _create_default_config() -> None:
    """Create a default config file with documentation."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    default_config = {
        "# _docs": "MyCLI Configuration — See https://mycli.dev/docs/config",
        "format": "table",
        "timeout": 30,
        "color": True,
        "verbose": False,
        "profile": "default",
        "output_dir": ".",
    }
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)
    CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"Created default config at {CONFIG_FILE}")


if __name__ == "__main__":
    main()
```

```python
# === 7. EXAMPLE USAGE ===

# Config file: ~/.config/mycli/config.yaml
# ---
# format: json
# profile: production
# timeout: 60
#
# Config file: ~/.config/mycli/profiles/production.yaml
# ---
# format: json
# timeout: 120
# output_dir: /var/log/mycli

# Environment variables:
#   MYCLI_FORMAT=yaml
#   MYCLI_TIMEOUT=90
#   MYCLI_PROFILE=staging

# Command line (highest precedence):
#   mycli --format table --timeout 5 deploy app-123

# Resolution for 'format' when all sources are set:
#   Default: table
#   Config file: json       # Overrides default
#   Profile: (same as file) # No override
#   Env var: yaml           # Overrides config file
#   Flag: table             # Overrides env var ← FINAL VALUE
```

```yaml
# === 8. DEFAULT CONFIG FILE TEMPLATE ===
# ~/.config/mycli/config.yaml — generated by `mycli config init`

# MyCLI Configuration
# See https://mycli.dev/docs/config for full documentation

# Output format: table, json, or yaml
format: table

# Network timeout in seconds
timeout: 30

# Enable color output
color: true

# Verbose logging
verbose: false

# Active profile (see ~/.config/mycli/profiles/)
profile: default

# Default output directory
output_dir: "."

# Custom API endpoint override
# api_endpoint: https://api.mycli.dev
```