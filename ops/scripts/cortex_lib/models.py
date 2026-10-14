#!/usr/bin/env python3
"""
cortex_lib/models.py — Shared model configuration loader (canonical, Hermes-independent).

Canonical home of the model-config logic in hermes_models.py, moved so no fleet
component requires the Hermes runtime to resolve it (component-hermes-separation
S1c). `hermes_models` remains as a thin re-export shim.

All Ollama model names used across the project are configured in
~/hermes-cortex/.env (preferred) or ~/.hermes/models.env (legacy fallback),
which survive cortex-update.sh (they're outside the repo).
This module provides a single importable function that every script uses,
replacing scattered hardcoded constants with a unified lookup.

Resolution priority (highest to lowest):
  1. Runtime environment variable (os.environ) — for one-off overrides
  2. ~/hermes-cortex/.env — unified config file (new, preferred)
  3. ~/.hermes/models.env — legacy model-only config (fallback)
  4. Hardcoded default — shipped with the repo, always the last fallback

Defined env vars (see ~/hermes-cortex/.env for current values):
  JUDGE_MODEL       — LLM-as-judge scorer (default: qwen2.5:3b)
  EMBEDDING_MODEL   — Text embeddings (default: nomic-embed-text)
  CODING_MODEL      — Code generation via offline_code (default: auto-detected)
  CREATIVE_MODEL    — Creative/text generation (consumer: agent-daily-bible-reading.py,
                      which reads it with get_model() and guards it with qualify_model())

Usage:
    from cortex_lib.models import get_model
    from hermes_models import get_model  # back-compat shim

    judge = get_model("JUDGE_MODEL", "qwen2.5:3b")
    embed = get_model("EMBEDDING_MODEL", "nomic-embed-text:v1.5")
"""

import os
import sys

_HERMES_CORTEX_ENV = os.path.expanduser("~/hermes-cortex/.env")
_LEGACY_MODELS_ENV = os.path.expanduser("~/.hermes/models.env")
_CACHE = None


def _load_env_file(path: str) -> dict[str, str]:
    """Load KEY=value pairs from a simple env file (no ``export`` keyword)."""
    result: dict[str, str] = {}
    if not os.path.isfile(path):
        return result
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, val = line.partition("=")
                    result[key.strip()] = val.strip().strip("'\"").strip()
    except (OSError, IOError) as exc:
        # The file's ABSENCE is a supported state (handled above); a present-but-unreadable
        # file is a real problem that would otherwise show up as "every model silently
        # reverted to its default" — say so rather than returning an empty config.
        print(f"WARNING: cannot read {path}: {exc}", file=sys.stderr)
    return result


def load_models_env() -> dict[str, str]:
    """Load model env vars from ~/hermes-cortex/.env (preferred),
    falling back to ~/.hermes/models.env (legacy).

    Returns a dict of KEY=value pairs.  Results are cached after first read.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    # Try the new unified file first, then the legacy file
    result = _load_env_file(_HERMES_CORTEX_ENV)
    if not result:
        result = _load_env_file(_LEGACY_MODELS_ENV)

    _CACHE = result
    return _CACHE


def get_model(env_var: str, default: str) -> str:
    """Resolve a model name from env var → env files → default.

    Args:
        env_var: Name of the environment variable (e.g. "JUDGE_MODEL").
        default: Hardcoded fallback shipped with the repo.

    Returns:
        The resolved model name string.
    """
    models_env = load_models_env()
    return models_env.get(env_var) or os.environ.get(env_var) or default


def qualify_model(value: str, default: str, *, endpoint: str = "") -> str:
    """Guard a model id that an HTTP endpoint addresses as ``provider/model``.

    CREATIVE_MODEL is the fleet's *creative* text path and its consumer reaches a remote
    OpenAI-compatible endpoint (agent-daily-bible-reading.py). Its value lives in a
    per-host ``~/hermes-cortex/.env``, so a host may carry a *bare* Ollama-style id
    (``deepseek-v4-flash``) that the endpoint cannot resolve. Rather than send an
    unusable id upstream and fail the run, fall back to ``default`` and say so on
    stderr — a silent substitution would hide a real config mistake.

    Callers read the contract with ``get_model()`` (the form the fleet's consumer scan
    recognises) and hand the resolved value here.

    Args:
        value: The resolved model id.
        default: Provider-qualified fallback (e.g. "deepseek/deepseek-chat").
        endpoint: Endpoint the id will be sent to (for the warning only).

    Returns:
        A provider-qualified model id.
    """
    if "/" in value:
        return value
    print(
        f"WARNING: {value!r} is not a provider-qualified model id "
        f"(expected 'provider/model'); using {default!r}"
        + (f" against {endpoint}" if endpoint else ""),
        file=sys.stderr,
    )
    return default


def _clear_cache() -> None:
    """Clear the cached hermes-cortex.env contents (for testing)."""
    global _CACHE
    _CACHE = None
