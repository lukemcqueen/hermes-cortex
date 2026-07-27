#!/usr/bin/env python3
"""
secret-leak-watchdog.py — no_agent cron job

Scans recent cron outputs and session directories for credential-like
patterns that indicate an agent leaked a secret via printf, echo, or
inline credentials in a terminal() command. When found, writes an inbox
alert so the orchestrator can investigate.

Runs as a no_agent cron — no LLM tokens, outputs silently when clean.

Patterns detected:
  - printf '<string-with-special-chars>'  (likely password leak)
  - echo '<long-string>' | piped to tool  (likely token leak)
  - curl -u 'user:longpass'               (inline basic auth)
  - VAR='<long-random-string>' in scripts (hardcoded secret)
"""

import json
import os
import re
import glob
import subprocess
import time
from pathlib import Path

# ── Config ──────────────────────────────────────────────────
HOME = os.path.expanduser("~")
CORTEX_HOME = os.environ.get("CORTEX_DEPLOY_HOME", f"{HOME}/.hermes-cortex")
CRON_OUTPUT_DIR = f"{HOME}/.hermes/cron/output"
SESSION_DIR = f"{CORTEX_HOME}/sessions"
STATE_FILE = f"{CORTEX_HOME}/state/.secret-leak-watchdog-state.json"
LOOKBACK_HOURS = int(os.environ.get("WATCHDOG_LOOKBACK_HOURS", "6"))
MAX_ALERTS = int(os.environ.get("WATCHDOG_MAX_ALERTS", "5"))

# Patterns to detect
PATTERNS = [
    # printf 'text-with-special-chars' > file
    (r"""printf\s+'[^']*[!@#$%^&*()\-+=][^']*'\s*(?:[|>]|>>)""",
     "printf+redirect with credential-like literal"),
    # printf "text-with-special-chars" > file
    (r'''printf\s+"[^"]*[!@#$%^&*()\-+=][^"]*"\s*(?:[|>]|>>)''',
     "printf+redirect with credential-like literal"),
    # echo 'long-token' | piped to tool
    (r"""echo\s+'[A-Za-z0-9_\-]{20,}'\s*\|""",
     "echo with long token-like string piped to tool"),
    # curl -u 'user:longpass'
    (r"""curl\s+.*\s-u\s+'[^']+:[^']{8,}'""",
     "inline credentials in curl command"),
    # Variable assignment with literal 20+ char string
    (r"""(?:^|export\s+)[A-Z_]+\s*=\s*'[A-Za-z0-9_!@#$%^&*()\-+=]{20,}'""",
     "literal secret value in variable assignment"),
    # gh auth login --with-token with inline token
    (r"""gh\s+auth\s+login\s+--with-token\s+['\"][A-Za-z0-9_\-]{20,}['\"]""",
     "inline GitHub token passed to gh auth login"),
]


def load_state():
    """Load previous scan state (mtime of last scanned file)."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_mtime": 0.0, "reported_findings": []}


def save_state(state):
    """Persist scan state."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def scan_file(path, patterns):
    """Scan a single file for credential-like patterns. Returns list of findings."""
    findings = []
    try:
        with open(path, "r", errors="replace") as f:
            content = f.read()
    except (OSError, PermissionError):
        return findings

    lines = content.split("\n")
    for idx, line in enumerate(lines, 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*"):
            continue
        for pattern, desc in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                # Truncate the line for safety (don't display the full secret)
                display = line.strip()[:80] + ("..." if len(line.strip()) > 80 else "")
                findings.append({
                    "file": path,
                    "line": idx,
                    "pattern": desc,
                    "preview": display,
                })
                break  # One alert per line
    return findings


def main():
    state = load_state()
    last_mtime = state.get("last_mtime", 0.0)
    cutoff = time.time() - (LOOKBACK_HOURS * 3600)
    all_findings = []

    # Scan cron output files (most likely place for leaked secrets)
    if os.path.isdir(CRON_OUTPUT_DIR):
        for path in glob.glob(f"{CRON_OUTPUT_DIR}/**/*", recursive=True):
            if not os.path.isfile(path):
                continue
            mtime = os.path.getmtime(path)
            if mtime < cutoff or mtime <= last_mtime:
                continue
            findings = scan_file(path, PATTERNS)
            for f in findings:
                f["source"] = "cron_output"
                f["mtime"] = mtime
            all_findings.extend(findings)

    # Also scan recent session files
    if os.path.isdir(SESSION_DIR):
        for path in glob.glob(f"{SESSION_DIR}/**/*.md", recursive=True):
            if not os.path.isfile(path):
                continue
            mtime = os.path.getmtime(path)
            if mtime < cutoff or mtime <= last_mtime:
                continue
            findings = scan_file(path, PATTERNS)
            for f in findings:
                f["source"] = "session"
                f["mtime"] = mtime
            all_findings.extend(findings)

    if not all_findings:
        # Clean — update state and exit silently
        newest = max(
            [os.path.getmtime(p) for p in glob.glob(f"{CRON_OUTPUT_DIR}/**/*", recursive=True) if os.path.isfile(p)] +
            [os.path.getmtime(p) for p in glob.glob(f"{SESSION_DIR}/**/*.md", recursive=True) if os.path.isfile(p)] +
            [last_mtime],
        )
        save_state({"last_mtime": newest, "reported_findings": []})
        return  # Silent exit — nothing to report

    # Deduplicate against previously reported findings
    prev_reported = set(
        (f["file"], f["line"]) for f in state.get("reported_findings", [])
    )
    new_findings = [
        f for f in all_findings
        if (f["file"], f["line"]) not in prev_reported
    ]

    if not new_findings:
        # Everything was already reported — just update state
        save_state({
            "last_mtime": time.time(),
            "reported_findings": state.get("reported_findings", []),
        })
        return  # Silent exit

    # Cap alerts
    new_findings = new_findings[:MAX_ALERTS]

    # Build alert message
    lines = ["⚠️  SECRET LEAK DETECTED", ""]
    for f in new_findings:
        rel_path = f["file"].replace(HOME, "~")
        lines.append(f"• [{f['source']}] {rel_path}:{f['line']}")
        lines.append(f"  Pattern: {f['pattern']}")
        lines.append(f"  `{f['preview']}`")
        lines.append("")

    lines.append(f"→ Run `secret-leak-remediate.sh` to investigate.")
    lines.append("→ Fix: use `$(cat <file>)` instead of printf/echo with literals.")

    # Output to stdout for the no_agent cron to deliver
    print("\n".join(lines))

    # Update state
    all_reported = state.get("reported_findings", [])
    all_reported.extend(new_findings)
    # Keep only last 100
    if len(all_reported) > 100:
        all_reported = all_reported[-100:]
    save_state({
        "last_mtime": time.time(),
        "reported_findings": all_reported,
    })


if __name__ == "__main__":
    main()
