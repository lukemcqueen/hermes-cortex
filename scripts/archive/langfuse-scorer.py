#!/usr/bin/env python3
"""Langfuse Auto-Scorer — evaluates Hermes conversation traces.

Reads unscored traces from Langfuse and posts quality scores.

Two modes:
  1. Rule-based (default) — heuristic scoring using response metrics
  2. LLM-assisted — uses Langfuse evaluator config if set up

Usage:
  python3 ~/.hermes/scripts/langfuse-scorer.py
  python3 ~/.hermes/scripts/langfuse-scorer.py --trace-id <id>
  python3 ~/.hermes/scripts/langfuse-scorer.py --dry-run
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from base64 import b64encode
from datetime import datetime, timezone, timedelta

# ── Config ──────────────────────────────────────────────────────────────
LANGFUSE_BASE = "http://localhost:3000"
SCORE_CRITERIA = ["helpfulness", "clarity", "depth"]
MAX_TRACES_PER_RUN = 10
MAX_CONTENT_CHARS = 2000


# ── Langfuse auth ──────────────────────────────────────────────────────
def _get_langfuse_keys():
    with open('~/.env', 'rb') as f:  # Example path — replace with your Langfuse .env location
        raw = f.read()
    pk = sk = None
    for line in raw.split(b'\n'):
        parts = line.split(b'=', 1)
        if len(parts) == 2:
            key, val = parts[0].decode(), parts[1].decode()
            if key == 'LANGFUSE_INIT_PROJECT_PUBLIC_KEY':
                pk = val
            elif key == 'LANGFUSE_INIT_PROJECT_SECRET_KEY':
                sk = val
    return pk, sk


def _lf_headers():
    pk, sk = _get_langfuse_keys()
    if not pk or not sk:
        print("ERROR: Could not read Langfuse project keys", file=sys.stderr)
        sys.exit(1)
    auth = b64encode(f"{pk}:{sk}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}


def _lf_get(path):
    headers = _lf_headers()
    req = urllib.request.Request(f"{LANGFUSE_BASE}{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  GET {path}: HTTP {e.code} — {body[:100]}", file=sys.stderr)
        return None


def _lf_post(path, body):
    headers = _lf_headers()
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{LANGFUSE_BASE}{path}", data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  POST {path}: HTTP {e.code} — {body[:200]}", file=sys.stderr)
        return None


# ── Rule-based scoring ─────────────────────────────────────────────────
def _score_by_rules(input_text: str, output_text: str, metadata: dict) -> dict:
    """Score a conversation turn using heuristics — no LLM needed."""
    inp_len = len(input_text or "")
    out_len = len(output_text or "")

    # ── helpfulness (1-5) ──
    # Based on response-to-input ratio and substance
    if out_len < 10:
        helpfulness = 1  # Barely responded
    elif out_len > inp_len * 10 and out_len > 1000:
        helpfulness = 5  # Comprehensive response
    elif out_len > inp_len * 5 and out_len > 500:
        helpfulness = 4  # Good depth
    elif out_len > inp_len * 2 or out_len > 200:
        helpfulness = 3  # Adequate
    elif out_len > 50:
        helpfulness = 2  # Minimal
    else:
        helpfulness = 1

    # ── clarity (1-5) ──
    # Based on structure markers in the response
    output_lower = (output_text or "").lower()
    markers = 0
    if "**" in (output_text or ""):
        markers += 1  # Bold formatting
    if "* " in (output_text or ""):
        markers += 1  # Bullet points
    if any(m in output_lower for m in ["\n1.", "\n2.", "\n3."]):
        markers += 1  # Numbered lists
    if any(h in output_lower for h in ["##", "**", "\n###"]):
        markers += 1  # Headers
    if markers >= 3:
        clarity = 5
    elif markers >= 2:
        clarity = 4
    elif markers >= 1:
        clarity = 3
    elif out_len > 100:
        clarity = 2
    else:
        clarity = 1

    # ── depth (1-5) ──
    # Based on response length and details
    tool_call_count = metadata.get("tool_call_count", 0)
    depth_score = 1
    if out_len > 5000:
        depth_score = 5
    elif out_len > 2000:
        depth_score = 4
    elif out_len > 500:
        depth_score = 3
    elif out_len > 100:
        depth_score = 2
    
    # Bonus for multiple tool calls (means research was done)
    if tool_call_count >= 5:
        depth_score = min(5, depth_score + 2)
    elif tool_call_count >= 2:
        depth_score = min(5, depth_score + 1)

    # ── overall (1-10) ──
    overall = round((helpfulness + clarity + depth_score) / 15 * 10)
    overall = max(1, min(10, overall))

    # ── comment ──
    comment_parts = []
    if out_len > 5000:
        comment_parts.append("comprehensive")
    elif out_len < 50:
        comment_parts.append("brief")
    if markers >= 2:
        comment_parts.append("well-structured")
    if tool_call_count >= 3:
        comment_parts.append("research-backed")

    return {
        "helpfulness": helpfulness,
        "clarity": clarity,
        "depth": depth_score,
        "overall_score": overall,
        "comment": "; ".join(comment_parts) if comment_parts else "auto-scored",
    }


# ── Scoring logic ───────────────────────────────────────────────────────
def _get_existing_score_names(trace_id: str) -> set:
    scores = _lf_get(f"/api/public/scores?traceId={trace_id}")
    if not scores:
        return set()
    return {s.get("name") for s in scores.get("data", [])}


def _post_scores(trace_id: str, scores: dict, dry_run: bool = False):
    if dry_run:
        print(f"  [DRY RUN] Would post scores: {json.dumps(scores)}")
        return True
    results = []
    for criterion in SCORE_CRITERIA:
        result = _lf_post("/api/public/scores", {
            "traceId": trace_id,
            "name": criterion,
            "value": float(scores[criterion]),
            "comment": f"auto-score ({criterion})",
        })
        if result:
            results.append(result)
        time.sleep(0.1)
    result = _lf_post("/api/public/scores", {
        "traceId": trace_id,
        "name": "overall",
        "value": float(scores["overall_score"]),
        "comment": scores.get("comment", ""),
    })
    if result:
        results.append(result)
    return len(results) >= 3


def _extract_trace_content(trace: dict) -> tuple:
    inp = trace.get("input", "")
    out = trace.get("output", "")
    trace_id = trace.get("id")

    # Try observations if trace-level content is empty
    if (not inp or not out) and trace_id:
        obs = _lf_get(f"/api/public/traces/{trace_id}/observations")
        if obs:
            for o in obs.get("data", []):
                if o.get("input") and not inp:
                    inp = o.get("input", "")
                if o.get("output") and not out:
                    out = o.get("output", "")

    # Serialize complex types
    if isinstance(inp, (dict, list)):
        inp = json.dumps(inp, default=str)[:MAX_CONTENT_CHARS]
    if isinstance(out, (dict, list)):
        out = json.dumps(out, default=str)[:MAX_CONTENT_CHARS]

    inp = str(inp or "")[:MAX_CONTENT_CHARS]
    out = str(out or "")[:MAX_CONTENT_CHARS]
    return inp, out


def main():
    dry_run = "--dry-run" in sys.argv
    specific_trace = None
    for arg in sys.argv[1:]:
        if arg.startswith("--trace-id="):
            specific_trace = arg.split("=", 1)[1]

    if specific_trace:
        traces_data = _lf_get(f"/api/public/traces?traceId={specific_trace}")
    else:
        traces_data = _lf_get(f"/api/public/traces?limit={MAX_TRACES_PER_RUN}")

    if not traces_data:
        print("Could not fetch traces from Langfuse")
        sys.exit(1)

    traces = traces_data.get("data", [])
    print(f"Langfuse traces available: {len(traces)}")
    print(f"Scoring mode: rule-based heuristics (no LLM needed)")

    scored = 0
    skipped = 0
    failed = 0

    for trace in traces:
        trace_id = trace.get("id")
        trace_name = trace.get("name", "unnamed")
        ts = str(trace.get("timestamp", ""))[:19]
        if not trace_id:
            continue

        existing = _get_existing_score_names(trace_id)
        if "overall" in existing and not specific_trace:
            skipped += 1
            continue

        print(f"\nScoring: [{ts}] {trace_name} ({trace_id[:16]}...)")

        inp, out = _extract_trace_content(trace)
        if not inp and not out:
            print("  No conversation content, skipping")
            skipped += 1
            continue

        metadata = {
            "tool_call_count": len(trace.get("observations", [])) if isinstance(trace.get("observations"), list) else 0,
        }
        print(f"  Input: {len(inp)} chars, Output: {len(out)} chars")

        scores = _score_by_rules(inp, out, metadata)
        print(f"  Scores: helpfulness={scores['helpfulness']} clarity={scores['clarity']} "
              f"depth={scores['depth']} overall={scores['overall_score']}")
        print(f"  Comment: {scores.get('comment', '')}")

        ok = _post_scores(trace_id, scores, dry_run=dry_run)
        if ok:
            scored += 1
            print("  ✅ Scores posted")
        else:
            failed += 1
            print("  ❌ Failed to post scores")

        time.sleep(0.3)

    print(f"\n{'─' * 40}")
    print(f"Results: {scored} scored, {skipped} skipped, {failed} failed")
    if dry_run:
        print("(Dry run — no scores were actually posted)")

    summary = {
        "timestamp": datetime.now().isoformat(),
        "scored": scored,
        "skipped": skipped,
        "failed": failed,
        "mode": "rule-based",
    }
    summary_path = os.path.expanduser("~/.hermes/cron/output/_scorer_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
