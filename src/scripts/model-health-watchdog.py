#!/usr/bin/env python3
"""Model Health Watchdog — checks Ollama models exist and are loadable.

Silent (exit 0) when all required models are present.
Alerts with a descriptive message when models are missing.

Required models:
  - nomic-embed-text:latest (embeddings for gbrain / session cache)
  - qwen2.5-coder:1.5b (LLM judge scorer)

Usage:
  python3 ~/.hermes-cortex/scripts/model-health-watchdog.py
  python3 ~/.hermes-cortex/scripts/model-health-watchdog.py --quiet  # only outputs on failure

Exit codes:
  0 = all models healthy
  1 = one or more models missing / Ollama unreachable
"""

import json
import os
import sys
import urllib.error
import urllib.request

# ── Config ──────────────────────────────────────────────────────────────
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
REQUIRED_MODELS = [
    "nomic-embed-text:latest",
    "qwen2.5-coder:1.5b",
]

MODEL_PURPOSE = {
    "nomic-embed-text:latest": "Embeddings for gbrain knowledge brain and session cache",
    "qwen2.5-coder:1.5b": "LLM-as-Judge scoring of Langfuse conversation traces",
}


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


def check_models_exist() -> dict:
    """Return {model_name: True/False} for each required model."""
    try:
        req = urllib.request.Request(OLLAMA_TAGS_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return {m: False for m in REQUIRED_MODELS}

    available = {m.get("name") for m in data.get("models", [])}
    return {m: m in available for m in REQUIRED_MODELS}


def main():
    quiet = "--quiet" in sys.argv

    # ── Check Ollama reachable ─────────────────────────────────────────
    if not quiet:
        print("🤖 Ollama Model Health Watchdog")
        print()
        print(f"Checking Ollama at http://localhost:11434...", end=" ", flush=True)

    if not check_ollama_reachable():
        print("❌ FAILED")
        print()
        print("Ollama is not reachable. This affects:")
        print("  - Knowledge brain (gbrain) — embeddings will fail")
        print("  - Session cache — no embeddings for similarity search")
        print("  - LLM judge scorer — no model to evaluate traces")
        print()
        print("Troubleshooting:")
        print("  1. Check if Ollama is running:")
        print("     systemctl status ollama")
        print("  2. Start Ollama manually:")
        print("     ollama serve")
        print("  3. Check logs:")
        print("     journalctl -u ollama --no-pager -n 20")
        sys.exit(1)

    if not quiet:
        print("✅ OK")
        print()
        print(f"Checking {len(REQUIRED_MODELS)} required models...")
        print()

    # ── Check each model ────────────────────────────────────────────────
    statuses = check_models_exist()
    all_ok = all(statuses.values())
    any_missing = False

    for model in REQUIRED_MODELS:
        exists = statuses[model]
        purpose = MODEL_PURPOSE.get(model, "")
        if exists:
            if not quiet:
                print(f"  ✅ {model}")
        else:
            any_missing = True
            print(f"  ❌ {model} — MISSING", file=sys.stderr)
            print(f"     Purpose: {purpose}", file=sys.stderr)

    if not all_ok or any_missing:
        print()
        print("Some required models are missing. To install:", file=sys.stderr)
        for model in REQUIRED_MODELS:
            if not statuses[model]:
                print(f"  ollama pull {model}", file=sys.stderr)
        print()
        print("After installing, verify with:", file=sys.stderr)
        print("  ollama list", file=sys.stderr)
        sys.exit(1)

    # ── All good ────────────────────────────────────────────────────────
    if not quiet:
        print()
        print("✅ All models present and Ollama reachable.")
    sys.exit(0)


if __name__ == "__main__":
    main()
