#!/usr/bin/env python3
"""Run gbrain doctor and output a concise summary for the morning briefing.

Avoids the pipe-to-interpreter security flag by running as a standalone script.
Usage: PATH="$HOME/.bun/bin:$PATH" python3 ~/.hermes/scripts/gbrain-doctor-summary.py
"""

import json
import subprocess
import sys
import os

def run_doctor():
    """Run gbrain doctor --json and return parsed output."""
    env = os.environ.copy()
    env["PATH"] = f"{os.path.expanduser('~/.bun/bin')}:{env.get('PATH', '')}"
    
    try:
        result = subprocess.run(
            ["gbrain", "doctor", "--json"],
            capture_output=True, text=True, timeout=60,
            env=env, cwd=os.path.expanduser("~/brain")
        )
        if result.returncode != 0:
            # Try non-JSON mode
            result2 = subprocess.run(
                ["gbrain", "doctor"],
                capture_output=True, text=True, timeout=60,
                env=env, cwd=os.path.expanduser("~/brain")
            )
            return {"raw_text": result2.stdout + result2.stderr, "json": None}
        
        return {"raw_text": None, "json": json.loads(result.stdout)}
    except json.JSONDecodeError as e:
        return {"raw_text": f"JSON parse error: {e}", "json": None}
    except FileNotFoundError:
        return {"raw_text": "gbrain not found in PATH", "json": None}
    except subprocess.TimeoutExpired:
        return {"raw_text": "gbrain doctor timed out after 60s", "json": None}
    except Exception as e:
        return {"raw_text": f"Error: {e}", "json": None}


def summarize_json(data):
    """Extract key metrics from JSON doctor output."""
    lines = []
    
    overall = data.get("overall_health_score", "N/A")
    lines.append(f"Overall health: {overall}/100")
    
    brain_score = data.get("brain_score", {})
    bs = brain_score.get("score", "N/A") if isinstance(brain_score, dict) else "N/A"
    lines.append(f"Brain score: {bs}/100")
    
    # Key checks
    checks = data.get("doctor", {}).get("checks", [])
    key_checks = ["cycle_freshness", "sync_freshness", "embedding_provider", 
                   "brain_score", "embed_staleness", "orphan_ratio",
                   "pack_upgrade_available", "frontmatter_integrity"]
    
    failures = []
    warnings = []
    
    for check in checks:
        name = check.get("name", "?")
        status = check.get("status", "?")
        msg = check.get("message", "")
        
        if status == "fail":
            failures.append(f"  ❌ {name}: {msg[:150]}")
        elif status == "warn" and name in key_checks:
            warnings.append(f"  ⚠️  {name}: {msg[:150]}")
    
    if failures:
        lines.append("\nFailures:")
        lines.extend(failures)
    if warnings:
        lines.append("\nKey warnings:")
        lines.extend(warnings)
    
    # Source freshness
    sync = [c for c in checks if c.get("name") == "sync_freshness"]
    if sync:
        lines.append(f"\nSync: {sync[0].get('message', 'N/A')}")
    
    cycle = [c for c in checks if c.get("name") == "cycle_freshness"]
    if cycle:
        lines.append(f"Cycle: {cycle[0].get('message', 'N/A')[:200]}")
    
    return "\n".join(lines)


def summarize_text(raw):
    """Extract key lines from text doctor output."""
    lines = []
    for line in raw.split("\n"):
        stripped = line.strip()
        if any(kw in stripped for kw in ["Overall health", "Brain score", 
                                          "[FAIL]", "[WARN]", "sync_freshness",
                                          "cycle_freshness", "embedding_provider",
                                          "frontmatter_integrity"]):
            lines.append(stripped)
        elif "All 3 federated source" in stripped:
            lines.append(stripped)
    
    return "\n".join(lines[:20]) if lines else "(raw output too large — see full log)"


def main():
    result = run_doctor()
    
    if result.get("json"):
        print(summarize_json(result["json"]))
    elif result.get("raw_text"):
        print("(JSON mode unavailable — using text summary)")
        print(summarize_text(result["raw_text"]))
    else:
        print("(doctor check unavailable)")


if __name__ == "__main__":
    main()
