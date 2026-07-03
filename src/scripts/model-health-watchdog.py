#!/usr/bin/env python3
"""Model Health Watchdog — checks required Ollama models exist.

Always checks: nomic-embed-text:v1.5 (embeddings for gbrain / session cache).
Checks one or more judge models — defaults to qwen2.5-coder:3b, but any
Ollama model name can be specified via --judge-model or JUDGE_MODEL env var.

Silent (exit 0) when all required models are present.
Alerts with a descriptive message when any model is missing.

Usage:
  # Default (nomic-embed-text:v1.5 + qwen2.5-coder:3b)
  python3 model-health-watchdog.py

  # Custom judge model (Titus using mannix/qwen2.5-coder:7b)
  python3 model-health-watchdog.py --judge-model mannix/qwen2.5-coder:7b-iq3_xs

  # Multiple judge models
  python3 model-health-watchdog.py --judge-model model-a --judge-model model-b

  # Via env var (comma-separated)
  JUDGE_MODEL=mannix/qwen2.5-coder:7b-iq3_xs python3 model-health-watchdog.py

  # Quiet mode — only outputs on failure
  python3 model-health-watchdog.py --quiet

Exit codes:
  0 = all models healthy
  1 = one or more models missing / Ollama unreachable
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

from hermes_models import get_model

# ── Config ──────────────────────────────────────────────────────────────
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
ALWAYS_REQUIRED = [
    ("nomic-embed-text:v1.5", "Embeddings for gbrain knowledge brain and session cache"),
]
DEFAULT_JUDGE_MODEL = "qwen2.5-coder:3b"


def _cron_ts(name: str) -> str:
    """Return non-LLM cron prefix: [YYYY-MM-DD HH:MM KST] <name>:"""
    kst = datetime.now(timezone(timedelta(hours=9))).strftime(
        "[%Y-%m-%d %H:%M KST]"
    )
    return f"{kst} {name}:"


def _parse_judge_models() -> list:
    """Read judge models from --judge-model args or JUDGE_MODEL env var.

    Priority: CLI --judge-model > JUDGE_MODEL env var > default.
    """
    # Scan CLI for --judge-model flags
    cli_models = []
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--judge-model" and i + 1 < len(args):
            cli_models.append(args[i + 1])
        elif arg.startswith("--judge-model="):
            cli_models.append(arg.split("=", 1)[1])

    if cli_models:
        return cli_models

    # Check env var (also falls back to ~/.hermes/models.env)
    env_models = get_model("JUDGE_MODEL", "").strip()
    if env_models:
        return [m.strip() for m in env_models.split(",") if m.strip()]

    # Default
    return [DEFAULT_JUDGE_MODEL]


def check_ollama_reachable() -> bool:
    """Verify Ollama server responds on the API endpoint."""
    try:
        req = urllib.request.Request(OLLAMA_TAGS_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            json.loads(resp.read().decode())
        return True
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} — {e.reason}", file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"  Connection refused — {e.reason}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  Unexpected error: {e}", file=sys.stderr)
        return False


def check_models_exist(models: list) -> dict:
    """Return {model_name: True/False} for each requested model."""
    try:
        req = urllib.request.Request(OLLAMA_TAGS_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return {m: False for m in models}

    available = {m.get("name") for m in data.get("models", [])}
    return {m: m in available for m in models}


def main():
    quiet = "--quiet" in sys.argv
    judge_models = _parse_judge_models()

    # Build full model list: always-required + judge models
    required = list(ALWAYS_REQUIRED)
    for jm in judge_models:
        required.append((jm, f"LLM-as-Judge scoring (configured as judge model)"))

    if not quiet:
        print(f"{_cron_ts('model-health-watchdog')} Checking Ollama at http://localhost:11434...", end=" ", flush=True)

    if not check_ollama_reachable():
        print("❌ FAILED")
        print()
        print(f"{_cron_ts('model-health-watchdog')} Ollama is not reachable. This affects:")
        print("  - Knowledge brain (gbrain) — embeddings will fail")
        print("  - Session cache — no embeddings for similarity search")
        print("  - LLM judge scorer — no model to evaluate traces")
        print()
        print("  Troubleshooting:")
        print("    1. Check if Ollama is running:")
        print("       systemctl status ollama")
        print("    2. Start Ollama manually:")
        print("       ollama serve")
        print("    3. Check logs:")
        print("       journalctl -u ollama --no-pager -n 20")
        sys.exit(1)

    if not quiet:
        print(f"  Looking for {len(required)} required models...")
        print()

    # ── Check each model ────────────────────────────────────────────────
    model_names = [m[0] for m in required]
    statuses = check_models_exist(model_names)
    all_ok = all(statuses.values())
    any_missing = False

    for model, purpose in required:
        exists = statuses.get(model, False)
        if exists:
            if not quiet:
                print(f"  ✅ {model}")
        else:
            any_missing = True
            print(f"{_cron_ts('model-health-watchdog')} ❌ {model} — MISSING", file=sys.stderr)
            print(f"     Purpose: {purpose}", file=sys.stderr)

    if not all_ok or any_missing:
        print()
        print(f"{_cron_ts('model-health-watchdog')} Some required models are missing. To install:", file=sys.stderr)
        for model in model_names:
            if not statuses.get(model, False):
                print(f"  ollama pull {model}", file=sys.stderr)
        print()
        print("After installing, verify with:", file=sys.stderr)
        print("  ollama list", file=sys.stderr)
        sys.exit(1)

    # ── All good ────────────────────────────────────────────────────────
    if not quiet:
        print()
        print(f"{_cron_ts('model-health-watchdog')} All models present and Ollama reachable.")
    sys.exit(0)


if __name__ == "__main__":
    main()
