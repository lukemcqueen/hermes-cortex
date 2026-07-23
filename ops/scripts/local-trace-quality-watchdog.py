#!/usr/bin/env python3
"""
trace-quality-watchdog.py — Alerts when LLM judge scores drop below threshold.

Queries Langfuse for recent scores. If any trace has overall < 4.0,
posts an alert with the trace details so you can review what went wrong.

Pattern: no_agent cron, silent on clean, delivers on concern.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import base64
from datetime import datetime, timedelta, timezone

ENV_PATH = os.path.expanduser("~/.hermes/.env")

QUALITY_THRESHOLD = 4.0  # overall score below this triggers alert
LOOKBACK_HOURS = 48      # check traces from last 48 hours

def load_env():
    """Load HERMES_LANGFUSE_* vars from .env."""
    env = {}
    if not os.path.exists(ENV_PATH):
        return env
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env

def get_auth(env):
    pk = env.get("HERMES_LANGFUSE_PUBLIC_KEY", "")
    sk = env.get("HERMES_LANGFUSE_SECRET_KEY", "")
    if not pk or not sk:
        return None
    return base64.b64encode(f"{pk}:{sk}".encode()).decode()

def langfuse_get(path, auth):
    """GET request to Langfuse API with retry."""
    url = f"http://localhost:3000/api/public/{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {auth}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return None

def main():
    env = load_env()
    auth = get_auth(env)
    if not auth:
        # No Langfuse configured — silent
        return

    since = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).isoformat()
    
    # Fetch scores from last LOOKBACK_HOURS
    scores = langfuse_get(
        f"scores?fromTimestamp={since}&name=overall&limit=100",
        auth
    )
    if not scores or not scores.get("data"):
        # No scores — might be a quiet period. Silent.
        return

    # Find low-scoring traces
    low_traces = []
    for s in scores["data"]:
        value = s.get("value", 10)
        if isinstance(value, (int, float)) and value < QUALITY_THRESHOLD:
            low_traces.append({
                "trace_id": s.get("traceId", "?"),
                "score": value,
                "timestamp": s.get("timestamp", "?")[:16],
                "name": s.get("name", "overall"),
            })

    if not low_traces:
        # All traces above threshold
        return

    # Deduplicate by trace_id, keep lowest score
    seen = {}
    for t in low_traces:
        tid = t["trace_id"]
        if tid not in seen or t["score"] < seen[tid]["score"]:
            seen[tid] = t

    # Fetch trace names
    traces_info = {}
    for tid in seen:
        trace = langfuse_get(f"traces/{tid}", auth)
        if trace:
            traces_info[tid] = {
                "name": trace.get("name", "?"),
                "input_preview": str(trace.get("input", ""))[:100] if trace.get("input") else "",
            }

    # Build alert
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"⚠️ **Trace Quality Alert** ({now})",
        f"Found {len(seen)} trace(s) with overall score < {QUALITY_THRESHOLD} in the last {LOOKBACK_HOURS}h:",
        ""
    ]
    
    for tid, info in sorted(seen.items(), key=lambda x: x[1]["score"]):
        trace_name = traces_info.get(tid, {}).get("name", "?")
        preview = traces_info.get(tid, {}).get("input_preview", "")
        lines.append(f"  • **{trace_name}** — overall: **{info['score']}/10**")
        lines.append(f"    Trace: `{tid[:20]}...`")
        if preview:
            lines.append(f"    Context: {preview}...")
        lines.append(f"    Langfuse: http://localhost:3000/trace/{tid}")
        lines.append("")
    
    lines.append(f"Review these in the Langfuse dashboard to understand quality dips.")
    
    sys.stdout.write("\n".join(lines) + "\n")

if __name__ == "__main__":
    main()
