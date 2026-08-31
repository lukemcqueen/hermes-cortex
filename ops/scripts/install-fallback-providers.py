#!/usr/bin/env python3
"""
install-fallback-providers.py

Ensures ~/.hermes/config.yaml has the fallback_providers chain:
  Tier 1: deepseek / deepseek-v4-flash (primary API fallback)
  Tier 2: opencode-zen / deepseek-v4-flash (OpenCode Zen relay fallback)

Chain is env-driven (sourced from ~/hermes-cortex/.env by the caller):
  LLM_CRON_FALLBACK1_MODEL / LLM_CRON_FALLBACK1_PROVIDER
  LLM_CRON_FALLBACK2_MODEL / LLM_CRON_FALLBACK2_PROVIDER

Idempotent — safe to run repeatedly. Only modifies config.yaml
if the fallback_providers section is missing or outdated.
"""

import os
import sys
import yaml
from pathlib import Path

HERMES_CONFIG = Path.home() / ".hermes" / "config.yaml"

# Desired fallback chain (env-driven — configure your own models in
# ~/hermes-cortex/.env; these are the fleet defaults). Entries whose
# model OR provider env var is empty are dropped — leave both empty to
# remove a tier.
def _env_entry(provider_var: str, model_var: str, provider_default: str, model_default: str, base_url: str | None = None, api_mode: str | None = None) -> dict | None:
    provider = os.environ.get(provider_var, provider_default).strip()
    model = os.environ.get(model_var, model_default).strip()
    if not provider or not model:
        return None
    entry = {"provider": provider, "model": model}
    if base_url:
        entry["base_url"] = base_url
    if api_mode:
        entry["api_mode"] = api_mode
    return entry


FALLBACK_PROVIDERS = [
    e
    for e in (
        _env_entry("LLM_CRON_FALLBACK1_PROVIDER", "LLM_CRON_FALLBACK1_MODEL", "deepseek", "deepseek-v4-flash"),
        _env_entry(
            "LLM_CRON_FALLBACK2_PROVIDER", "LLM_CRON_FALLBACK2_MODEL", "opencode-zen", "deepseek-v4-flash",
            base_url="https://opencode.ai/zen/v1", api_mode="chat_completions",
        ),
    )
    if e is not None
]


def load_config(path):
    """Load existing config or start fresh."""
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(path, cfg):
    """Write config back."""
    with open(path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
    print(f"✅ Updated {path}")


def main():
    if not HERMES_CONFIG.exists():
        print(f"❌ Config not found at {HERMES_CONFIG}")
        print("   Has hermes been initialized on this machine?")
        sys.exit(1)

    cfg = load_config(HERMES_CONFIG)
    existing = cfg.get("fallback_providers", [])

    if existing == FALLBACK_PROVIDERS:
        print(f"✓ fallback_providers already correct at {HERMES_CONFIG}")
        return

    cfg["fallback_providers"] = FALLBACK_PROVIDERS
    save_config(HERMES_CONFIG, cfg)

    print()
    for i, fb in enumerate(FALLBACK_PROVIDERS, 1):
        print(f"  Tier {i}: {fb['provider']} / {fb['model']}")


if __name__ == "__main__":
    main()
