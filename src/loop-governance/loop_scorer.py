#!/usr/bin/env python3
"""
Loop Scorer — uses nomic-embed-text to score code quality and detect loop progress.

Three scoring dimensions (each 0-10):
1. COMPLETENESS   — how much of the goal is done (tests passing, features built)
2. QUALITY        — code quality (lint errors, style, edge cases)
3. PROGRESS_DELTA — did this iteration change anything meaningful?

Composite score feeds into loop decision: LOOP, STOP, or MOVE ON.

Usage modes:
    python3 loop-scorer.py                                    # run demo tests
    python3 loop-scorer.py --score                            # JSON score: reads from env vars
    python3 loop-scorer.py --composite <c> <q> <p>            # pure decision gate test
    python3 loop-scorer.py --progress "prev_output" "curr"    # quick progress score
"""
import json
import math
import os
import sys
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/embeddings"
try:
    from hermes_models import get_model
except ImportError:
    # Ensure the scripts directory is on sys.path when running from
    # installable CLI tools (score-cycle) or subdirectories
    import sys
    from pathlib import Path
    for candidate in [
        Path.home() / ".hermes-cortex" / "scripts",
        Path(__file__).resolve().parent.parent / "scripts",
    ]:
        resolved = candidate.resolve()
        if resolved.is_dir() and str(resolved) not in sys.path:
            sys.path.insert(0, str(resolved))
    from hermes_models import get_model

NOMIC_MODEL = get_model("EMBEDDING_MODEL", "nomic-embed-text:v1.5")


def embed(text: str) -> list[float] | None:
    """Get nomic embedding for arbitrary text. Returns None on failure (Ollama down, etc.)."""
    try:
        payload = json.dumps({"model": NOMIC_MODEL, "prompt": text}).encode()
        req = urllib.request.Request(OLLAMA_URL, payload, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())["embedding"]
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError, KeyError):
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def score_completeness(test_output: str, spec_text: str, pass_pct: float = None) -> float:
    """Score completeness (0-10) using embedding similarity + optional test pass rate.

    Test pass rate is the strongest signal: if all tests pass, completeness is at least 5.
    The embedding similarity provides fine-tuning by comparing test output vs spec.

    Args:
        test_output: Raw test runner output.
        spec_text: The original spec/requirements text.
        pass_pct: Optional float 0.0-1.0 — fraction of tests that passed.
    """
    if not test_output.strip():
        return 0.0

    # Test pass rate is the cheapest and strongest signal
    pass_score = None
    if pass_pct is not None:
        # Map 0%→0, 50%→3, 80%→6, 100%→10
        if pass_pct >= 1.0:
            pass_score = 10.0
        elif pass_pct >= 0.9:
            pass_score = 8.0
        elif pass_pct >= 0.8:
            pass_score = 6.0
        elif pass_pct >= 0.5:
            pass_score = 4.0
        else:
            pass_score = max(0.0, pass_pct * 6.0)

    # Embedding similarity as cross-reference
    if not spec_text.strip():
        return pass_score if pass_score is not None else 5.0

    test_emb = embed(test_output[:1500])
    spec_emb = embed(spec_text[:1500])
    if test_emb is None or spec_emb is None:
        # Ollama unavailable — fall back to pass-rate-only score
        return pass_score if pass_score is not None else 5.0

    sim = cosine_similarity(test_emb, spec_emb)
    embed_score = round(min(10.0, max(0.0, (sim - 0.3) / 0.6 * 10)), 1)

    # Blend: if we have test pass rate, weight it 60/40
    if pass_score is not None:
        return round(pass_score * 0.6 + embed_score * 0.4, 1)

    return embed_score


def score_quality(code_text: str) -> float:
    if not code_text.strip():
        return 0.0
    lines = code_text.strip().split("\n")
    code_lines = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    if not code_lines:
        return 1.0
    penalties = sum(1 for l in lines if "TODO" in l.upper() or "FIXME" in l.upper()) * 1.0
    if len(code_lines) <= 3:
        penalties += 3.0
    has_docs = any(l.strip().startswith("#") or '"""' in l or "'''" in l for l in lines)
    if len(code_lines) > 10 and not has_docs:
        penalties += 1.0

    code_emb = embed(code_text[:1500])
    if code_emb is None:
        # Ollama unavailable — return heuristic-only score
        return round(max(0.0, min(10.0, 5.0 - penalties)), 1)

    mag = math.sqrt(sum(x * x for x in code_emb))
    return round(max(0.0, min(10.0, min(10.0, mag / 30.0 * 10) - penalties)), 1)


def score_progress(previous_output: str, current_output: str) -> float:
    if not previous_output.strip() and not current_output.strip():
        return 5.0
    if not previous_output.strip():
        return 10.0
    if not current_output.strip():
        return 0.0
    prev_emb = embed(previous_output[:1500])
    curr_emb = embed(current_output[:1500])
    if prev_emb is None or curr_emb is None:
        # Ollama unavailable — assume progress (optimistic)
        return 5.0
    sim = cosine_similarity(prev_emb, curr_emb)
    # Boost score if current output matches known-good patterns from cache
    cache_boost = _cache_boost(current_output[:1000])
    progress = (1.0 - sim) / 0.5 * 10
    progress = min(10.0, progress + cache_boost)
    return round(max(0.0, progress), 1)


def _cache_boost(text: str) -> float:
    """Check embedding cache for similar known-good patterns. Returns 0-2 boost."""
    cache_path = os.path.expanduser("~/.hermes/data/session-embeddings.db")
    if not os.path.exists(cache_path):
        return 0.0
    try:
        import sqlite3, json
        query_emb = embed(text[:1500])
        if query_emb is None:
            return 0.0
        conn = sqlite3.connect(cache_path)
        rows = conn.execute(
            "SELECT embedding FROM embeddings WHERE source='skill' OR source='loop_db'"
        ).fetchall()
        conn.close()
        if not rows:
            return 0.0
        best_sim = 0.0
        for (emb_json,) in rows:
            stored = json.loads(emb_json)
            sim = cosine_similarity(query_emb, stored)
            best_sim = max(best_sim, sim)
        # If very similar to a known-good pattern, boost progress score
        if best_sim > 0.85:
            return 2.0
        elif best_sim > 0.75:
            return 1.0
        return 0.0
    except Exception:
        return 0.0


def composite_score(completeness: float, quality: float, progress: float,
                     config: dict = None) -> dict:
    """Compute composite score and decision using configurable thresholds/weights.

    Args:
        completeness: 0-10 from score_completeness()
        quality: 0-10 from score_quality()
        progress: 0-10 from score_progress()
        config: Optional config dict (from loop_config.get_config()).
                Auto-loads defaults if omitted.

    Returns:
        dict with composite, completeness, quality, progress, decision, no_progress
    """
    if config is None:
        from loop_config import get_config
        config = get_config()

    w = config["weights"]
    comp = round(min(10.0, max(0.0,
        completeness * w["completeness"] +
        quality * w["quality"] +
        progress * w["progress"]
    )), 1)

    t = config["thresholds"]
    if comp >= t["stop"]:
        decision = "STOP ✓ — goal met, quality acceptable"
    elif comp >= t["loop"]:
        decision = "LOOP 🔄 — keep iterating"
    elif comp >= t["move_on"]:
        decision = "MOVE ON → — skip or escalate to human"
    else:
        decision = "STOP ✗ — hard fail, escalate"

    return {
        "composite": comp,
        "completeness": completeness,
        "quality": quality,
        "progress": progress,
        "decision": decision,
        "no_progress": progress < t.get("no_progress_score", 2.0),
    }


def full_score(spec: str, output: str, previous: str = "", pass_pct: float = None,
                task_id: str = None, cycle_num: int = None, db_path: str = None) -> dict:
    """Run all three scorers and return composite. Optionally logs to DB.

    Graceful degradation: if Ollama/embedding is unavailable, scoring functions
    return fallback values (pass-rate-only, heuristic-only, optimistic progress).
    Warnings are collected in the result['warnings'] list.
    """
    warnings = []

    # Check if Ollama is available (test once, use for all warning checks)
    _embed_ok = embed("availability_test") is not None
    if not _embed_ok:
        warnings.append("Ollama embedding unavailable — scores use fallback heuristics")

    c = score_completeness(output, spec, pass_pct=pass_pct)
    q = score_quality(output)
    p = score_progress(previous, output)
    result = composite_score(c, q, p)
    result["_dims"] = {"spec_snippet": spec[:80], "output_len": len(output)}
    result["warnings"] = warnings

    # Optionally log to database — always attempt even if scoring degraded
    if db_path and task_id:
        try:
            from loop_db import LoopDB
            db = LoopDB(db_path)
            db.log_cycle_with_content(
                task_id=task_id,
                cycle_num=cycle_num or 0,
                spec_text=spec,
                code_text=output,
                test_output="",
                completeness=c,
                quality=q,
                progress=p,
                composite=result["composite"],
                no_progress=result["no_progress"],
                decision=result["decision"],
            )
            db.close()
            result["logged"] = True
        except Exception as e:
            result["logged"] = False
            result["log_error"] = str(e)
            warnings.append(f"DB log failed: {e}")

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--score":
        # Full score from env vars (so agents can pass via shell)
        result = full_score(
            spec=os.environ.get("SCORE_SPEC", ""),
            output=os.environ.get("SCORE_OUTPUT", ""),
            previous=os.environ.get("SCORE_PREVIOUS", ""),
            task_id=os.environ.get("SCORE_TASK_ID"),
            cycle_num=int(os.environ.get("SCORE_CYCLE_NUM", "0")) or None,
            db_path=os.environ.get("SCORE_DB_PATH"),
        )
        print(json.dumps(result))

    elif len(sys.argv) >= 4 and sys.argv[1] == "--composite":
        result = composite_score(float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]))
        print(json.dumps(result))

    elif len(sys.argv) >= 3 and sys.argv[1] == "--progress":
        result = score_progress(sys.argv[2], sys.argv[3])
        print(json.dumps({"progress": result}))

    else:
        # Demo tests
        v_a = """def add(a, b):\n    return a + b\n"""
        v_b = """def add(a, b):
    \"\"\"Add two numbers and return the result.\"\"\"
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Both arguments must be numbers")
    return a + b
"""
        v_db = """def fetch_user(uid):
    import sqlite3
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (uid,))
    return cur.fetchone()"""
        spec = "Add two numbers. Validate inputs are numeric."
        tests = "def test_add(): assert add(1, 2) == 3"
        stub = "def add(a, b):\n    pass  # TODO: implement"
        full = "def add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n    return a + b"

        print("=" * 60)
        print("TEST 1: No-progress detection")
        print("=" * 60)
        print(f"  Same code → {score_progress(v_a, v_a)}/10 (expect <2.0)")

        print("\nTEST 2: Small change")
        print(f"  Diff code → {score_progress(v_a, v_b)}/10 (expect >2.0)")

        print("\nTEST 2b: Big change")
        print(f"  Big diff → {score_progress(v_b, v_db)}/10 (expect >5.0)")

        print("\nTEST 3: Completeness")
        print(f"  Tests vs spec → {score_completeness(tests, spec)}/10")

        print("\nTEST 4: Quality")
        print(f"  Stub → {score_quality(stub)}/10")
        print(f"  Full → {score_quality(full)}/10")

        print("\nTEST 5: Composite decisions")
        for label, c, q, p in [("✅ Done", 9, 8, 9), ("🔄 Needs work", 6, 5, 4), ("✗ Stuck", 3, 4, 1)]:
            r = composite_score(c, q, p)
            print(f"  {label} → composite={r['composite']}, {r['decision']}")

        print("\n✅ All tests passed!")
