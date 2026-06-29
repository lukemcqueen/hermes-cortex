---
language: python
tags: [configuration, env, 12-factor, secrets]
title: Environment Variable Patterns
description: Naming conventions, .env files, defaults, validation with pydantic-settings, 12-factor app principles, and secrets management
source: pattern
---

```python
# === 12-FACTOR APP — CONFIG VIA ENVIRONMENT VARIABLES ===
#
# Principle 3 of the 12-Factor App: "Store config in the environment."
# Strict separation of config from code — no config values in the repository.
#
# ✅ Environment variables are the single source of runtime config
# ✅ Never hardcode credentials, hostnames, or environment-specific values
# ✅ .env files are for local development ONLY — never committed

# NAMING CONVENTIONS:
# <APP_PREFIX>_<CATEGORY>_<KEY>
#
# App prefix:
#   MYAPP_ - general config
#   DB_    - database config
#   CACHE_ - cache/redis config
#   AWS_   - AWS service config
#   LOG_   - logging config
#
# Examples:
#   MYAPP_ENV=production
#   MYAPP_DEBUG=false
#   MYAPP_SECRET_KEY=<never-commit-this>
#   DB_HOST=postgres.example.com
#   DB_PORT=5432
#   DB_NAME=myapp_production
#   DB_USER=deploy
#   DB_PASSWORD=<never-commit-this>
#   REDIS_URL=redis://:password@redis.example.com:6379/0
#   AWS_REGION=us-east-1
#   AWS_ACCESS_KEY_ID=AKIA...
#   AWS_SECRET_ACCESS_KEY=<never-commit-this>
#   LOG_LEVEL=INFO
#   LOG_FORMAT=json
```

```python
# === .env FILE PATTERN (LOCAL DEVELOPMENT ONLY) ===

# .env — NEVER COMMIT TO VERSION CONTROL
# .env.example — COMMIT THIS (templates with dummy values, no secrets)

# .env.example
# Copy this to .env and fill in your local values.
# Never commit .env to version control.

# Application
MYAPP_ENV=development
MYAPP_DEBUG=true
MYAPP_SECRET_KEY=change-me-in-production
MYAPP_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=myapp_dev
DB_USER=postgres
DB_PASSWORD=postgres

# Redis
REDIS_URL=redis://localhost:6379/0

# External Services
SENDGRID_API_KEY=
STRIPE_API_KEY=
STRIPE_WEBHOOK_SECRET=

# Logging
LOG_LEVEL=DEBUG
LOG_FORMAT=pretty
```

```python
# === VALIDATION WITH PYDANTIC-SETTINGS (RECOMMENDED) ===

# pip install pydantic-settings

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, RedisDsn, field_validator, SecretStr
from typing import Literal
import os

class Settings(BaseSettings):
    """Application settings, validated and parsed from environment variables.

    Uses pydantic-settings which automatically reads from env vars and .env files.
    All values are validated at import time — app fails fast on misconfiguration.
    """

    # Application
    env: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias="MYAPP_ENV",
    )
    debug: bool = Field(default=False, validation_alias="MYAPP_DEBUG")
    secret_key: SecretStr = Field(..., validation_alias="MYAPP_SECRET_KEY")
    allowed_hosts: list[str] = Field(
        default=["localhost", "127.0.0.1"],
        validation_alias="MYAPP_ALLOWED_HOSTS",
    )

    # Database
    db_url: PostgresDsn = Field(..., validation_alias="DB_URL")
    db_pool_size: int = Field(default=10, ge=1, le=100, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, validation_alias="DB_MAX_OVERFLOW")

    # Redis / Cache
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
    )

    # External APIs
    stripe_api_key: SecretStr | None = Field(
        default=None, validation_alias="STRIPE_API_KEY",
    )
    sendgrid_api_key: SecretStr | None = Field(
        default=None, validation_alias="SENDGRID_API_KEY",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="LOG_LEVEL",
    )

    # Model configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Prevent .env from leaking into production — only env vars used
        # In production, don't deploy a .env file; rely on actual env vars
    )

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [host.strip() for host in v.split(",") if host.strip()]
        return v

    @field_validator("env")
    @classmethod
    def validate_production_debug(cls, v: str, info) -> str:
        """Prevent debug=True in production."""
        if v == "production" and info.data.get("debug"):
            raise ValueError("debug must be False in production environment")
        return v

# Single instance (singleton pattern — access via import)
settings = Settings()  # Reads from env vars + .env

# Usage anywhere in the app
from config import settings

def get_database_url() -> str:
    return str(settings.db_url)

# Accessing secret values safely
def configure_stripe():
    if settings.stripe_api_key:
        stripe.api_key = settings.stripe_api_key.get_secret_value()
    else:
        logger.warning("Stripe API key not configured — payments disabled")
```

```python
# === ACCESS PATTERNS ===

# Pattern A: Global singleton (simplest, recommended for most apps)
# config/__init__.py
from .settings import settings
__all__ = ["settings"]

# Usage: from config import settings

# Pattern B: Lazy loading (avoids import-time FS reads)
class LazySettings:
    _instance: Settings | None = None

    def __getattr__(self, name: str):
        if self._instance is None:
            self._instance = Settings()
        return getattr(self._instance, name)

# Usage: settings = LazySettings()  # reads .env on first access

# Pattern C: Environment-specific settings
class ProductionSettings(Settings):
    @property
    def debug(self) -> bool:
        return False  # Production always overrides to False

class DevelopmentSettings(Settings):
    model_config = SettingsConfigDict(env_file=".env")
```

```python
# === SECRETS MANAGEMENT (BEYOND ENV VARS) ===

# For production, env vars are fine for most config, but secrets should use a vault.

# Option 1: HashiCorp Vault
import hvac

class VaultBackedSettings:
    """Fetches secrets from Vault, falls back to env vars / defaults."""

    def __init__(self, vault_url: str, vault_token: str, mount_path: str = "secret"):
        self._client = hvac.Client(url=vault_url, token=vault_token)
        self._mount_path = mount_path
        self._secrets: dict = {}

    def get_secret(self, path: str, key: str, default: str | None = None) -> str:
        cache_key = f"{path}/{key}"
        if cache_key not in self._secrets:
            try:
                secret = self._client.secrets.kv.v2.read_secret_version(
                    path=path, mount_point=self._mount_path,
                )
                self._secrets[cache_key] = secret["data"]["data"].get(key, os.getenv(key, default))
            except Exception:
                self._secrets[cache_key] = os.getenv(key, default)
        return self._secrets[cache_key]


# Option 2: AWS Secrets Manager
import boto3
from botocore.exceptions import ClientError

class AWSSecretsManager:
    def __init__(self, region_name: str = "us-east-1"):
        self._client = boto3.client("secretsmanager", region_name=region_name)
        self._cache: dict[str, str] = {}

    def get_secret(self, secret_id: str) -> dict:
        if secret_id not in self._cache:
            try:
                response = self._client.get_secret_value(SecretId=secret_id)
                self._cache[secret_id] = json.loads(response["SecretString"])
            except ClientError as exc:
                raise RuntimeError(f"Failed to fetch secret '{secret_id}'") from exc
        return self._cache[secret_id]


# Option 3: Environment-only (simple but still secure with proper CI/CD)
# GitLab CI / GitHub Actions inject secrets as env vars at deploy time
# Never in .env files in production
# Never in source code
# Rotation handled by the platform

# .gitlab-ci.yml example
# variables:
#   MYAPP_SECRET_KEY: $MYAPP_SECRET_KEY  # CI/CD secret variable
#   DB_PASSWORD: $DB_PASSWORD
```