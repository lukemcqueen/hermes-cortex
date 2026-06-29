---
language: yaml
tags: [configuration, yaml, toml, environments]
title: Config File Formats
description: YAML vs TOML vs JSON comparison, hierarchical config, multi-environment configs (dev/staging/prod), and config merging strategies
source: pattern
---

```yaml
# === YAML (RECOMMENDED for hierarchical/multi-environment config) ===
# config/default.yaml — base configuration for all environments

app:
  name: myapp
  version: "1.0.0"
  host: 0.0.0.0
  port: 8080
  cors:
    allowed_origins:
      - "http://localhost:3000"
    allowed_methods:
      - GET
      - POST
      - PUT
      - DELETE
    allowed_headers:
      - Content-Type
      - Authorization
      - X-Correlation-ID

database:
  pool:
    min_size: 2
    max_size: 10
  connect_timeout: 5
  retry:
    max_attempts: 3
    backoff_base: 0.5

logging:
  level: INFO
  format: json
  output: stdout

features:
  signup:
    enabled: true
    require_email_verification: false
  analytics:
    enabled: true
    provider: posthog
```

```yaml
# config/development.yaml — overrides for local development

# Uses YAML anchors to reference and merge base config
<<: *default  # Merge with default.yaml (see *default anchor)

app:
  port: 8080
  cors:
    allowed_origins:
      - "http://localhost:3000"
      - "http://localhost:5173"

database:
  host: localhost
  port: 5432
  name: myapp_dev

logging:
  level: DEBUG
  format: pretty

features:
  signup:
    require_email_verification: false  # Disable email verification locally
```

```yaml
# config/production.yaml

app:
  host: 0.0.0.0
  port: 8080
  cors:
    allowed_origins:
      - "https://app.myapp.com"
      - "https://admin.myapp.com"
  workers: 4

database:
  # In production, connection details come from env vars or secrets manager
  connect_timeout: 10
  retry:
    max_attempts: 5
    backoff_base: 1.0

logging:
  level: INFO
  format: json
  output: stdout

features:
  signup:
    require_email_verification: true
  analytics:
    enabled: true
    provider: posthog
```

```python
# === PYTHON — YAML CONFIG LOADING WITH MERGING ===

# pip install pyyaml
import os
import yaml
from pathlib import Path
from typing import Any

class ConfigLoader:
    """Loads and merges multi-environment YAML configs.

    Precedence (highest wins):
      1. Environment-specific overrides (production/development.yaml)
      2. Local overrides (config.local.yaml — never committed)
      3. Defaults (config/default.yaml)
    """

    CONFIG_DIR = Path("config")

    def __init__(self, env: str | None = None):
        self._env = env or os.getenv("MYAPP_ENV", "development")
        self._data: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """Load and merge config files in order of precedence."""

        # 1. Load defaults
        default_path = self.CONFIG_DIR / "default.yaml"
        if default_path.exists():
            with open(default_path) as f:
                self._deep_merge(yaml.safe_load(f) or {})

        # 2. Override with environment-specific config
        env_path = self.CONFIG_DIR / f"{self._env}.yaml"
        if env_path.exists():
            with open(env_path) as f:
                self._deep_merge(yaml.safe_load(f) or {})

        # 3. Override with local overrides (NOT committed to VCS)
        local_path = self.CONFIG_DIR / "config.local.yaml"
        if local_path.exists():
            with open(local_path) as f:
                self._deep_merge(yaml.safe_load(f) or {})

        return self._data

    def _deep_merge(self, overlay: dict) -> None:
        """Recursively merge overlay into self._data."""
        for key, value in overlay.items():
            if (
                key in self._data
                and isinstance(self._data[key], dict)
                and isinstance(value, dict)
            ):
                self._deep_merge(value)
            else:
                self._data[key] = value

# Usage
config = ConfigLoader(env="production").load()
db_host = config["database"]["host"]
```

```toml
# === TOML (PREFERRED for Python pyproject.toml / simple configs) ===
# config.toml

[app]
name = "myapp"
version = "1.0.0"
host = "0.0.0.0"
port = 8080

[app.cors]
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
]

[database]
host = "localhost"
port = 5432
name = "myapp_dev"
pool_min = 2
pool_max = 10

[database.retry]
max_attempts = 3
backoff_base = 0.5

[logging]
level = "DEBUG"
format = "json"
output = "stdout"

[features.signup]
enabled = true
require_email_verification = false

[features.analytics]
enabled = true
provider = "posthog"

# TOML notes:
# - Type-safe (strings, integers, floats, booleans, dates, arrays, tables)
# - Great for simple, flat config structures
# - Less ergonomic for deeply nested or multi-environment configs
# - Native support in Python (import tomllib in 3.11+), Rust, Go
```

```json
{
  "//": "JSON — NOT RECOMMENDED for hand-written config files",
  "//": "No comments allowed, no trailing commas, easy to break",
  "//": "Use for machine-generated config (e.g., package.json, tsconfig.json)",
  "app": {
    "name": "myapp",
    "version": "1.0.0",
    "port": 8080
  },
  "database": {
    "host": "localhost",
    "port": 5432,
    "pool": {
      "min": 2,
      "max": 10
    }
  }
}
```

```yaml
# === MULTI-ENVIRONMENT CONFIG PATTERN (single file) ===
# config/multienv.yaml — all environments in one file with shared defaults

shared: &shared
  app:
    name: myapp
    version: "1.0.0"
    host: 0.0.0.0
  database:
    connect_timeout: 5
  logging:
    output: stdout

development:
  <<: *shared
  app:
    port: 8080
    debug: true
  database:
    host: localhost
    port: 5432
    name: myapp_dev
  logging:
    level: DEBUG
    format: pretty

staging:
  <<: *shared
  app:
    port: 8080
    debug: false
  database:
    host: staging-db.internal
    port: 5432
    name: myapp_staging
  logging:
    level: INFO
    format: json

production:
  <<: *shared
  app:
    port: 80
    workers: 4
    debug: false
  database:
    host: prod-db.internal
    port: 5432
    name: myapp_production
    pool:
      min_size: 5
      max_size: 20
    retry:
      max_attempts: 5
  logging:
    level: INFO
    format: json
```

```python
# === PYTHON — LOADING SINGLE-FILE MULTI-ENV CONFIG ===

class MultiEnvConfigLoader:
    """Loads environment-specific section from a multi-env YAML file."""

    def __init__(self, config_path: str, env: str | None = None):
        self._path = Path(config_path)
        self._env = env or os.getenv("MYAPP_ENV", "development")

    def load(self) -> dict:
        with open(self._path) as f:
            all_config = yaml.safe_load(f)

        if self._env not in all_config:
            available = list(all_config.keys())
            raise ConfigError(
                f"Environment '{self._env}' not found in {self._path}. "
                f"Available: {available}"
            )

        return all_config[self._env]

# Example: config = MultiEnvConfigLoader("config/multienv.yaml", "staging").load()
```

```yaml
# === ENVIRONMENT VARIABLE SUBSTITUTION IN CONFIG FILES ===

# config/default.yaml with env var substitution
# Use placeholder syntax for values that come from env vars

app:
  secret_key: "${MYAPP_SECRET_KEY}"  # Will be resolved at load time
  host: "${MYAPP_HOST:-0.0.0.0}"     # Supports default value syntax
  port: "${MYAPP_PORT:-8080}"

database:
  url: "postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

logging:
  level: "${LOG_LEVEL:-INFO}"
```

```python
# === PYTHON — ENV VAR SUBSTITUTION ===

import os
import re
from typing import Any

class EnvSubstConfigLoader:
    """Loads config with environment variable substitution."""

    ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::-(.+))?\}")

    @classmethod
    def resolve_env_vars(cls, value: Any) -> Any:
        """Recursively resolve ${VAR} and ${VAR:-default} patterns."""
        if isinstance(value, str):
            def _replace(match: re.Match) -> str:
                var_name = match.group(1)
                default = match.group(2)
                return os.environ.get(var_name, default or "")
            return cls.ENV_PATTERN.sub(_replace, value)
        elif isinstance(value, dict):
            return {k: cls.resolve_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [cls.resolve_env_vars(item) for item in value]
        return value

# Usage
with open("config/default.yaml") as f:
    raw = yaml.safe_load(f)
    config = EnvSubstConfigLoader.resolve_env_vars(raw)
```

```yaml
# === FORMAT COMPARISON ===

# Recommendation:
# YAML — Best for: multi-environment, hierarchical, human-edited config files
# TOML — Best for: flat configs, pyproject.toml, Rust Cargo.toml
# JSON — Best for: machine-generated config, package.json, API payloads
# INI  — Legacy, avoid unless required by an existing tool

# Feature matrix:
#          YAML  TOML  JSON  INI
# Comments  ✅    ✅    ❌   ✅
# Nested    ✅    ✅    ✅   ❌
# Types     ⚠️   ✅    ✅   ❌
# Multi-doc ✅    ❌    ❌   ❌
# Anchors   ✅    ❌    ❌   ❌
# Readable  ✅    ✅    ⚠️   ✅
```