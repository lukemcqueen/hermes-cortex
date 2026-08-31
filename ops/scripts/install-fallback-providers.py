#!/usr/bin/env python3
"""
install-fallback-providers.py

Single source of truth for the fleet fallback chain in ~/.hermes/config.yaml.

Chain (env-driven, canonical defaults — every host converges to the same
chain even if its ~/hermes-cortex/.env is untouched):
  Tier 1: openrouter / deepseek/deepseek-v4-flash (cheapest relay)
  Tier 2: deepseek / deepseek-v4-flash (direct API)
  Tier 3: opencode-zen / deepseek-v4-flash (OpenCode Zen relay)

Per-host overrides (read from ~/hermes-cortex/.env, no caller sourcing needed):
  LLM_CRON_FALLBACK1_MODEL / LLM_CRON_FALLBACK1_PROVIDER
  LLM_CRON_FALLBACK2_MODEL / LLM_CRON_FALLBACK2_PROVIDER
  LLM_CRON_FALLBACK3_MODEL / LLM_CRON_FALLBACK3_PROVIDER

Writes via `hermes config set fallback_providers '<json>'` — the sanctioned
surgical path (preserves every other key/comment in config.yaml). Falls back
to a direct yaml edit only if the hermes CLI is missing.

Idempotent — safe to run repeatedly. Runs automatically from cortex-update.sh
so every fleet host converges the chain on every sync/deploy.
"""

import json
import os
import re
import subprocess
import sys
import yaml
from pathlib import Path

HERMES_CONFIG = Path.home() / ".hermes" / "config.yaml"
HC_ENV = Path.home() / "hermes-cortex" / ".env"

# Canonical fleet chain — the defaults every host converges to. Per-host
# overrides come from the env file above.
DEFAULT_FALLBACKS = [
    {
        "provider": "openrouter",
        "model": "deepseek/deepseek-v4-flash",
    },
    {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
    },
    {
        "provider": "opencode-zen",
        "model": "deepseek-v4-flash",
        "base_url": "https://opencode.ai/zen/v1",
        "api_mode": "chat_completions",
    },
]


def load_hc_env() -> dict:
    """Read KEY=VALUE pairs from ~/hermes-cortex/.env (no shell sourcing)."""
    result = {}
    if not HC_ENV.exists():
        return result
    try:
        for line in HC_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return result


def build_chain(env: dict) -> list[dict]:
    """Build the chain: per-host overrides win, canonical defaults otherwise."""
    chain = []
    for tier, (provider_var, model_var, default) in enumerate(
        (
            ("LLM_CRON_FALLBACK1_PROVIDER", "LLM_CRON_FALLBACK1_MODEL", DEFAULT_FALLBACKS[0]),
            ("LLM_CRON_FALLBACK2_PROVIDER", "LLM_CRON_FALLBACK2_MODEL", DEFAULT_FALLBACKS[1]),
            ("LLM_CRON_FALLBACK3_PROVIDER", "LLM_CRON_FALLBACK3_MODEL", DEFAULT_FALLBACKS[2]),
        ),
        1,
    ):
        provider = env.get(provider_var, "").strip()
        model = env.get(model_var, "").strip()
        if provider and model:
            entry = {"provider": provider, "model": model}
            # Keep base_url/api_mode from the canonical entry for the same
            # provider, so a provider-only override still hits the right relay.
            if provider == default.get("provider"):
                if default.get("base_url"):
                    entry["base_url"] = default["base_url"]
                if default.get("api_mode"):
                    entry["api_mode"] = default["api_mode"]
            chain.append(entry)
        elif not provider and not model:
            # Both empty → drop the tier (explicit removal).
            continue
        else:
            # One set, one empty → treat as unset, use the canonical default.
            chain.append(dict(default))
    return chain


def current_chain(cfg: dict) -> list[dict]:
    raw = cfg.get("fallback_providers") or []
    if isinstance(raw, dict):
        raw = [raw]
    return raw if isinstance(raw, list) else []


def apply_via_cli(chain: list[dict]) -> bool:
    """Apply via `hermes config set` — surgical, preserves other keys."""
    payload = json.dumps(chain, ensure_ascii=False)
    try:
        proc = subprocess.run(
            ["hermes", "config", "set", "fallback_providers", payload],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def apply_via_yaml(chain: list[dict]) -> bool:
    """Direct yaml fallback (hermes CLI missing) — key-only edit."""
    try:
        if not HERMES_CONFIG.exists():
            print(f"❌ Config not found at {HERMES_CONFIG}")
            return False
        cfg = yaml.safe_load(HERMES_CONFIG.read_text(encoding="utf-8")) or {}
        cfg["fallback_providers"] = chain
        HERMES_CONFIG.write_text(
            yaml.dump(cfg, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        return True
    except (OSError, yaml.YAMLError):
        return False


def main() -> int:
    if not HERMES_CONFIG.exists():
        print(f"❌ Config not found at {HERMES_CONFIG}")
        print("   Has hermes been initialized on this machine?")
        return 1

    try:
        cfg = yaml.safe_load(HERMES_CONFIG.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        print(f"❌ Could not read {HERMES_CONFIG}: {e}")
        return 1

    chain = build_chain(load_hc_env())

    if current_chain(cfg) == chain:
        print(f"✓ fallback_providers already correct at {HERMES_CONFIG}")
        return 0

    ok = apply_via_cli(chain) or apply_via_yaml(chain)
    if not ok:
        print(f"❌ Failed to write fallback_providers to {HERMES_CONFIG}")
        return 1

    print(f"✅ Updated {HERMES_CONFIG}")
    for i, fb in enumerate(chain, 1):
        print(f"  Tier {i}: {fb['provider']} / {fb['model']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
