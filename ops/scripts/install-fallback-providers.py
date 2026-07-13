#!/usr/bin/env python3
"""
install-fallback-providers.py

Ensures ~/.hermes/config.yaml has the fallback_providers chain:
  Tier 1: opencode-zen / deepseek-v4-flash (free API fallback)
  Tier 2: custom:ollama-local / qwen2.5-coder:3b (local last resort)

Idempotent — safe to run repeatedly. Only modifies config.yaml
if the fallback_providers section is missing or outdated.
"""

import os
import sys
import yaml
from pathlib import Path

HERMES_CONFIG = Path.home() / ".hermes" / "config.yaml"

# Desired fallback chain (model-agnostic in intent — configure your own models)
FALLBACK_PROVIDERS = [
    {
        "provider": "opencode-zen",
        "model": "deepseek-v4-flash",
        "base_url": "https://opencode.ai/zen/v1",
        "api_mode": "chat_completions",
    },
    {
        "provider": "custom:ollama-local",
        "model": "qwen2.5-coder:3b",
    },
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
