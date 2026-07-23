"""
Helpers — utility functions for running commands, HTTP checks, process detection, and name suggestions.
"""

import json
import os
import subprocess
from pathlib import Path

from .config import CURL


def run(cmd, timeout=10):
    """Run a shell command, return (output, exit_code)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except FileNotFoundError:
        return "", -1
    except subprocess.TimeoutExpired:
        return "(timed out)", -1


def run_bg(cmd, timeout=10):
    """Run command, return output, ignore errors."""
    out, _ = run(cmd, timeout=timeout)
    return out


def http_get(url, timeout=10):
    """Curl-based HTTP check (with -k for localhost SSL)."""
    out, _ = run(
        [CURL, "-sk", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url]
    )
    return out.strip()


def read_file(path):
    """Read a file, returning empty string on error."""
    try:
        return Path(path).read_text()
    except (FileNotFoundError, OSError):
        return ""


def process_running(name):
    """Check if a process matching name is running via pgrep."""
    out = run_bg(["pgrep", "-f", name], timeout=5)
    return bool(out.strip())


def find_similar_name(name, valid_names):
    """Suggest a similar cron name from valid_names if one exists."""
    if not name or not valid_names:
        return None
    base = name.replace("-cron", "").replace("-daemon", "").replace("-job", "")
    for v in valid_names:
        if v == name:
            return None
        if v == base:
            return v
    norm = name.replace("_", "-").replace(" ", "-").lower()
    for v in valid_names:
        v_norm = v.replace("_", "-").replace(" ", "-").lower()
        if v_norm == norm:
            return v
    for v in valid_names:
        if abs(len(v) - len(name)) <= 2:
            diffs = sum(1 for a, b in zip(v, name) if a != b) + abs(len(v) - len(name))
            if diffs <= 2:
                return v
    for v in valid_names:
        if name.startswith(v) or v.startswith(name):
            return v
        if name.endswith(v) or v.endswith(name):
            return v
    return None
