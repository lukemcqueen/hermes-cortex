#!/usr/bin/env python3
"""
hermes_models.py — Shared model configuration loader for all Hermes Cortex scripts.

All environment variables used across the project are configured in
~/hermes-cortex/.env, which is gitignored and never overwritten by
cortex-update.sh. This module provides a single importable function
that every script uses, replacing scattered hardcoded constants with
a unified lookup.

Resolution priority (highest to lowest):
  1. Runtime environment variable (os.environ) — for one-off overrides
  2. ~/hermes-cortex/.env — persistent per-agent config, never overwritten
  3. Hardcoded default — shipped with the repo, always the fallback

Defined env vars (see ~/hermes-cortex/.env for current values):
  JUDGE_MODEL       — LLM-as-judge scorer (default: qwen2.5-coder:3b)
  EMBEDDING_MODEL   — Text embeddings (default: nomic-embed-text)
  CODING_MODEL      — Code generation via offline_code (default: auto-detected)
  CREATIVE_MODEL    — Reserved for creative/text generation (no default yet)

Usage:
    from hermes_models import get_model

    judge = get_model("JUDGE_MODEL", "qwen2.5-coder:3b")
    embed = get_model("EMBEDDING_MODEL", "nomic-embed-text:v1.5")
"""

import os

_MODELS_ENV_PATH = os.path.expanduser("~/hermes-cortex/.env")
_CACHE: dict | None = None


def load_models_env() -> dict[str, str]:
    """Load env vars from ~/hermes-cortex/.env.

    Returns a dict of KEY=value pairs.  Non-existent or unreadable files
    return an empty dict silently.  Results are cached after first read.

    The file uses ``KEY=value`` syntax (no ``export`` keyword).  Lines
    starting with ``#`` are treated as comments and ignored.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    if not os.path.isfile(_MODELS_ENV_PATH):
        _CACHE = {}
        return _CACHE

    result: dict[str, str] = {}
    try:
        with open(_MODELS_ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    result[key.strip()] = val.strip()
        _CACHE = result
    except (OSError, IOError):
        _CACHE = {}
    return _CACHE


def get_model(env_var: str, default: str) -> str:
    """Resolve a model name from env var → .env → default.

    Args:
        env_var: Name of the environment variable (e.g. "JUDGE_MODEL").
        default: Hardcoded fallback shipped with the repo.

    Returns:
        The resolved model name string.
    """
    # Runtime env var wins first (one-off overrides)
    runtime = os.environ.get(env_var)
    if runtime:
        return runtime
    # Then .env file
    models_env = load_models_env()
    return models_env.get(env_var) or default


def _clear_cache() -> None:
    """Clear the cached .env contents (for testing)."""
    global _CACHE
    _CACHE = None
