#!/usr/bin/env python3
"""LLM-as-Judge Scorer — evaluates Hermes conversation traces using a local Ollama model.

Replaces the earlier rule-based scorer with actual LLM-based judgment.
Uses local Ollama model (default: qwen2.5-coder:3b) for evaluation, posts scores to Langfuse API.
Configurable via JUDGE_MODEL constant at the top of this file and checked
at startup via _check_ollama_model().

Usage:
  python3 ~/.hermes-cortex/scripts/llm-judge-scorer.py
  python3 ~/.hermes-cortex/scripts/llm-judge-scorer.py --trace-id <id>
  python3 ~/.hermes-cortex/scripts/llm-judge-scorer.py --dry-run
  python3 ~/.hermes-cortex/scripts/llm-judge-scorer.py --env-path ~/langfuse/.env
"""

import json, os, re, sys, time, urllib.request, urllib.error
from base64 import b64encode
from datetime import datetime, timedelta, timezone

from hermes_models import get_model

# ── Config ──────────────────────────────────────────────────────────────
LANGFUSE_BASE = "http://localhost:3000"
OLLAMA_BASE = "http://localhost:11434"
OLLAMA_API_TAGS = f"{OLLAMA_BASE}/api/tags"
OLLAMA_URL = f"{OLLAMA_BASE}/api/chat"

JUDGE_MODEL = get_model("JUDGE_MODEL", "qwen2.5-coder:3b")

SCORE_CRITERIA = ["helpfulness", "clarity", "depth"]
MAX_TRACES_PER_RUN = 5  # ~3min on Intel with qwen2.5-coder:3b
MAX_CONTENT_CHARS = 800  # Keep small for CPU-bound inference
FETCH_BATCH = 20  # Fetch this many, filter to unscored


# ── Prerequisite checks ────────────────────────────────────────────────
def _check_ollama_model() -> None:
    """Verify the judge model exists in Ollama before starting. Exit cleanly if not."""
    try:
        req = urllib.request.Request(OLLAMA_API_TAGS)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"ERROR: Cannot reach Ollama at {OLLAMA_BASE} (HTTP {e.code})", file=sys.stderr)
        print(f"  Is Ollama running? Check: systemctl status ollama", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Cannot connect to Ollama at {OLLAMA_BASE}: {e.reason}", file=sys.stderr)
        print(f"  Is Ollama running? Try: ollama serve", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error contacting Ollama: {e}", file=sys.stderr)
        sys.exit(1)

    available = {m.get("name") for m in data.get("models", [])}
    if JUDGE_MODEL not in available:
        print(f"ERROR: Judge model '{JUDGE_MODEL}' not found in Ollama", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"  Available models: {', '.join(sorted(available)) or '(none)'}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"  To install:", file=sys.stderr)
        print(f"    ollama pull {JUDGE_MODEL}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"  To verify after install:", file=sys.stderr)
        print(f"    ollama list | grep {JUDGE_MODEL.replace(':', ' ')}", file=sys.stderr)
        sys.exit(1)


# ── Langfuse auth ──────────────────────────────────────────────────────
def _get_langfuse_keys():
    """Read Langfuse project keys from a configurable .env file.

    Priority: --env-path CLI arg > LANGFUSE_ENV_PATH env var > ~/.hermes-cortex/.env
    """
    env_path = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg.startswith("--env-path="):
            env_path = arg.split("=", 1)[1]
            break
        if arg == "--env-path" and i + 1 < len(args):
            env_path = args[i + 1]
            break
    if not env_path:
        env_path = os.environ.get("LANGFUSE_ENV_PATH")
    if not env_path:
        env_path = os.path.expanduser("~/.hermes/.env")
    if env_path:
        env_path = os.path.expanduser(env_path)

    try:
        with open(env_path, 'rb') as f:
            raw = f.read()
    except FileNotFoundError:
        return None, None
    pk = sk = None
    for line in raw.split(b'\n'):
        line = line.strip()
        if b'#' in line:
            line = line[:line.index(b'#')].strip()
        parts = line.split(b'=', 1)
        if len(parts) == 2:
            key, val = parts[0].decode().strip(), parts[1].decode().strip()
            # Strip optional quotes
            val = val.strip("'\"")
            if key == 'LANGFUSE_INIT_PROJECT_PUBLIC_KEY' or key == 'HERMES_LANGFUSE_PUBLIC_KEY':
                pk = val
            elif key == 'LANGFUSE_INIT_PROJECT_SECRET_KEY' or key == 'HERMES_LANGFUSE_SECRET_KEY':
                sk = val
    return pk, sk


def _lf_headers():
    pk, sk = _get_langfuse_keys()
    if not pk or not sk:
        print("ERROR: Could not read Langfuse project keys", file=sys.stderr)
        sys.exit(1)
    auth = b64encode(f"{pk}:{sk}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}


def _lf_get(path, retries=2):
    """GET from Langfuse API. Retries on transient errors (connection reset, timeout)."""
    headers = _lf_headers()
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(f"{LANGFUSE_BASE}{path}", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  GET {path}: HTTP {e.code} — {body[:100]}", file=sys.stderr)
            return None
        except urllib.error.URLError as e:
            last_err = e
            print(f"  GET {path}: connection failed (attempt {attempt+1}) — {e.reason}", file=sys.stderr)
        except OSError as e:  # catches ConnectionResetError, ConnectionAbortedError, etc.
            last_err = e
            print(f"  GET {path}: socket error (attempt {attempt+1}) — {e}", file=sys.stderr)
        if attempt < retries - 1:
            time.sleep(2)
    if last_err:
        print(f"  GET {path}: giving up after {retries} attempts", file=sys.stderr)
    return None


def _lf_post(path, body, retries=2):
    """POST to Langfuse API. Retries on transient errors."""
    headers = _lf_headers()
    last_err = None
    for attempt in range(retries):
        data = json.dumps(body).encode()
        req = urllib.request.Request(f"{LANGFUSE_BASE}{path}", data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  POST {path}: HTTP {e.code} — {body[:200]}", file=sys.stderr)
            return None
        except urllib.error.URLError as e:
            last_err = e
            print(f"  POST {path}: connection failed (attempt {attempt+1}) — {e.reason}", file=sys.stderr)
        except OSError as e:
            last_err = e
            print(f"  POST {path}: socket error (attempt {attempt+1}) — {e}", file=sys.stderr)
        if attempt < retries - 1:
            time.sleep(2)
    if last_err:
        print(f"  POST {path}: giving up after {retries} attempts", file=sys.stderr)
    return None


# ── LLM-as-Judge scoring ───────────────────────────────────────────────
EVAL_SYSTEM_PROMPT = """You are an expert evaluator scoring AI assistant responses. Your task is to assess the quality of an assistant's response using a detailed rubric.

Scoring criteria:
1. helpfulness (1-5): How well does the response address the user's question or request? Is it complete, relevant, and directly useful?
2. clarity (1-5): Is the response well-structured, easy to read, and well-formatted? Does it use formatting appropriately (lists, bold, headers)?
3. depth (1-5): Does the response provide sufficient detail and substance? Does it go beyond surface-level answers when appropriate?

Overall score (1-10): A holistic assessment of the response's quality combining all factors.

Return ONLY a valid JSON object with these exact keys."""


def _call_judge(input_text: str, output_text: str) -> dict:
    """Send a trace to the LLM judge and get scored evaluation."""
    # Truncate to keep prompt manageable
    inp = str(input_text or "")[:MAX_CONTENT_CHARS]
    out = str(output_text or "")[:MAX_CONTENT_CHARS]

    user_prompt = f"""Evaluate this assistant response:

## User Input
{inp}

## Assistant Output
{out}

## Scoring
Rate each criterion 1-5, and overall 1-10.

Return this exact JSON format:
{{"helpfulness": <int>, "clarity": <int>, "depth": <int>, "overall_score": <int>, "reasoning": "<brief justification>"}}"""

    payload = json.dumps({
        "model": JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": EVAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 4096}
    }).encode()

    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        resp = json.loads(r.read().decode())

    content = resp["message"]["content"]
    match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in judge output: {content[:200]}")

    result = json.loads(match.group())
    # Validate keys
    for key in ["helpfulness", "clarity", "depth", "overall_score"]:
        if key not in result:
            result[key] = 3  # default fallback
    return result


# ── Scoring pipeline ────────────────────────────────────────────────────
def _get_existing_score_names(trace_id: str) -> set:
    scores = _lf_get(f"/api/public/scores?traceId={trace_id}")
    if not scores:
        return set()
    return {s.get("name") for s in scores.get("data", [])}


def _post_scores(trace_id: str, scores: dict, comment: str, dry_run: bool = False):
    if dry_run:
        print(f"  [DRY RUN] Would post: {json.dumps(scores)}")
        return True
    results = []
    for criterion in SCORE_CRITERIA:
        result = _lf_post("/api/public/scores", {
            "traceId": trace_id,
            "name": criterion,
            "value": float(scores[criterion]),
            "comment": f"llm-judge: {scores.get('reasoning', '')[:100]}",
        })
        if result:
            results.append(result)
        time.sleep(0.1)
    result = _lf_post("/api/public/scores", {
        "traceId": trace_id,
        "name": "overall",
        "value": float(scores["overall_score"]),
        "comment": comment,
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

    return str(inp or "")[:MAX_CONTENT_CHARS], str(out or "")[:MAX_CONTENT_CHARS]


# ── Summary persistence ─────────────────────────────────────────────────
def _save_summary(scored: int, skipped: int, failed: int, model: str):
    summary = {
        "timestamp": datetime.now().isoformat(),
        "scored": scored,
        "skipped": skipped,
        "failed": failed,
        "mode": f"llm-judge-{model}",
        "elapsed_seconds": 0,
    }
    summary_path = os.path.expanduser("~/.hermes/cron/output/_scorer_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)


# ── Main ────────────────────────────────────────────────────────────────
def main():
    dry_run = "--dry-run" in sys.argv
    quiet = "--quiet" in sys.argv
    specific_trace = None
    for arg in sys.argv[1:]:
        if arg.startswith("--trace-id="):
            specific_trace = arg.split("=", 1)[1]

    if not quiet:
        print(f"🧠 LLM-as-Judge Scorer")
        print(f"   Model: {JUDGE_MODEL}")
        print(f"   Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        print()

    # Verify prerequisites before starting
    _check_ollama_model()

    # Fetch traces — fetch in bulk to find unscored ones
    if specific_trace:
        # Single trace via direct endpoint
        trace_data = _lf_get(f"/api/public/traces/{specific_trace}")
        traces = [trace_data] if trace_data and trace_data.get("id") else []
    else:
        # Fetch enough to find MAX_TRACES_PER_RUN unscored
        all_traces = []
        seen_ids = set()
        limit = min(FETCH_BATCH, 50)
        from_ts = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()[:19] + "Z"
        traces_data = _lf_get(f"/api/public/traces?fromTimestamp={from_ts}&limit={limit}")
        candidates = traces_data.get("data", []) if traces_data else []
        for t in candidates:
            tid = t.get("id")
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                existing = _get_existing_score_names(tid)
                if "overall" not in existing:
                    all_traces.append(t)
                    if len(all_traces) >= MAX_TRACES_PER_RUN:
                        break
        traces = all_traces[:MAX_TRACES_PER_RUN]

    # Auto-quiet: zero output when there's nothing to score (all traces already scored)
    if len(traces) == 0:
        _save_summary(0, 0, 0, JUDGE_MODEL)
        return

    if not quiet:
        print(f"Langfuse traces fetched: {len(traces)}")
        print()

    scored = 0
    skipped = 0
    failed = 0

    for trace in traces:
        trace_id = trace.get("id")
        trace_name = trace.get("name", "unnamed")
        ts = str(trace.get("timestamp", ""))[:19]
        if not trace_id:
            continue

        # Skip already-scored traces (unless specific trace requested)
        existing = _get_existing_score_names(trace_id)
        if "overall" in existing and not specific_trace:
            skipped += 1
            continue

        print(f"━━━ [{ts}] {trace_name}")
        print(f"     Trace: {trace_id[:16]}...")

        inp, out = _extract_trace_content(trace)
        if not inp and not out:
            print(f"     ⏭ No conversation content, skipping")
            skipped += 1
            continue

        print(f"     Content: {len(inp)} chars in → {len(out)} chars out")
        print(f"     Judging with {JUDGE_MODEL}...", end=" ", flush=True)

        try:
            t0 = time.time()
            scores = _call_judge(inp, out)
            elapsed = time.time() - t0
            print(f"done ({elapsed:.0f}s)")
            print(f"     Scores: helpfulness={scores['helpfulness']} clarity={scores['clarity']} "
                  f"depth={scores['depth']} overall={scores['overall_score']}")
            print(f"     Reason: {scores.get('reasoning', '')[:120]}")

            ok = _post_scores(trace_id, scores, scores.get("reasoning", ""), dry_run=dry_run)
            if ok:
                scored += 1
                print(f"     ✅ Posted to Langfuse")
            else:
                failed += 1
                print(f"     ❌ Failed to post")

        except Exception as e:
            failed += 1
            print(f"     ❌ Judge error: {e}")

        time.sleep(0.5)

    if not quiet or scored > 0:
        print()
    if not quiet or scored > 0:
        print(f"{'═' * 40}")
        print(f"Results: {scored} scored, {skipped} skipped, {failed} failed")
        if dry_run:
            print("(Dry run — no scores were actually posted)")

    _save_summary(scored, skipped, failed, JUDGE_MODEL)


if __name__ == "__main__":
    main()
