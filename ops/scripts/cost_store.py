"""
Cron job cost tracking store.

SQLite-backed store for per-run token usage and estimated cost.
Stored alongside cron output under ~/.hermes/cron/cron-costs.db.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from cron.jobs import CRON_DIR, _secure_file

logger = logging.getLogger(__name__)

# Lazy-init to avoid import-time filesystem dependency
_db: Optional[sqlite3.Connection] = None
_db_lock = threading.Lock()
_DB_PATH = CRON_DIR / "cron-costs.db"

# ── Rate versioning (O1-S1, HC gaps party 2026-08-21) ─────────────
# Every row carries the pricing schedule that produced its
# estimated_cost_usd. Rows stamped with an older version can be
# re-priced at current rates via reprice_runs() / `--reprice`.
# Canonical prices live in ops/scripts/manage/orch-daily-cost-report.py
# (same constants — keep in sync).
RATE_VERSION = "2026-08-16"  # DeepSeek hike effective date (2.5x hit, 1.57x miss, 2.36x out)
PRICE_HIT = 0.007    # USD per 1M cache-hit input tokens
PRICE_MISS = 0.22    # USD per 1M cache-miss input tokens
PRICE_OUT = 0.66     # USD per 1M output tokens
PEAK_MULT = 2.0      # DeepSeek peak-hour multiplier


def _is_peak_hour(dt) -> bool:
    """DeepSeek peak: 01:00-04:00 and 06:00-10:00 UTC."""
    h = dt.hour
    return (1 <= h < 4) or (6 <= h < 10)


def _compute_cost(input_tok, output_tok, cache_read_tok, cache_write_tok, run_dt) -> float:
    """Estimate USD at current rates.

    NOTE — cron-costs.db semantics differ from usage_audit.jsonl:
    `input_tokens` here is ALREADY the cache-MISS portion
    (usage_pricing.py: input_tokens = max(0, prompt_total - hit - write)),
    so miss = input + write. usage_audit's `prompt_tokens` is TOTAL
    (hit + miss), which is why orch-daily-cost-report.py computes
    miss = max(prompt - hit, 0) there. Do not unify them blindly.
    """
    hit = cache_read_tok or 0
    miss = (input_tok or 0) + (cache_write_tok or 0)
    mult = PEAK_MULT if _is_peak_hour(run_dt) else 1.0
    return (hit * PRICE_HIT + miss * PRICE_MISS + (output_tok or 0) * PRICE_OUT) * mult / 1e6


def _get_db() -> sqlite3.Connection:
    """Lazy-init SQLite connection. Thread-safe."""
    global _db
    if _db is not None:
        return _db
    with _db_lock:
        if _db is not None:
            return _db
        CRON_DIR.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA synchronous=NORMAL")
        _db.executescript("""
            CREATE TABLE IF NOT EXISTS cron_runs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id        TEXT NOT NULL,
                run_time      TEXT NOT NULL,
                input_tokens  INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens  INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                api_calls     INTEGER DEFAULT 0,
                estimated_cost_usd REAL DEFAULT 0.0,
                model         TEXT,
                provider      TEXT,
                no_agent      INTEGER DEFAULT 0,
                status        TEXT DEFAULT 'ok',
                rate_version  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_cron_runs_job_id ON cron_runs(job_id);
            CREATE INDEX IF NOT EXISTS idx_cron_runs_run_time ON cron_runs(run_time);
        """)
        # Migration for pre-existing DBs (O1-S1): add rate_version if missing.
        cols = [r[1] for r in _db.execute("PRAGMA table_info(cron_runs)").fetchall()]
        if "rate_version" not in cols:
            _db.execute("ALTER TABLE cron_runs ADD COLUMN rate_version TEXT")
            _db.commit()
            logger.info("Migrated cron_runs: added rate_version column")
        _secure_file(_DB_PATH)
        return _db


def record_run(job_id: str, cost_data: Dict[str, Any]) -> None:
    """Record a cron run's token usage and cost.

    Args:
        job_id: The cron job ID.
        cost_data: Dict with keys:
            input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
            api_calls, estimated_cost_usd, model, provider, no_agent, status
    """
    try:
        db = _get_db()
        db.execute(
            """INSERT INTO cron_runs
               (job_id, run_time, input_tokens, output_tokens,
                cache_read_tokens, cache_write_tokens, api_calls,
                estimated_cost_usd, model, provider, no_agent, status, rate_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                int(cost_data.get("input_tokens", 0)),
                int(cost_data.get("output_tokens", 0)),
                int(cost_data.get("cache_read_tokens", 0)),
                int(cost_data.get("cache_write_tokens", 0)),
                int(cost_data.get("api_calls", 0)),
                float(cost_data.get("estimated_cost_usd", 0.0)),
                str(cost_data.get("model") or "")[:100] or None,
                str(cost_data.get("provider") or "")[:100] or None,
                1 if cost_data.get("no_agent") else 0,
                str(cost_data.get("status", "ok"))[:20],
                str(cost_data.get("rate_version") or RATE_VERSION)[:20],
            ),
        )
        db.commit()
    except Exception as e:
        logger.warning("Failed to record cron cost for job '%s': %s", job_id, e)


def reprice_runs(days: Optional[int] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Re-price recorded runs at the current rate schedule.

    O1-S1: rows recorded under older pricing (pre 2026-08-16 DeepSeek hike)
    are re-priced from their token columns so historical comparisons are
    apples-to-apples. Stamps rate_version=RATE_VERSION on rows it re-prices.
    no_agent rows (cost=0) and rows without token data are left untouched.

    Args:
        days: Only re-price runs newer than this many days (None = all).
        dry_run: Compute new costs without writing.

    Returns:
        Dict with rows_scanned, rows_repriceable, rows_updated, cost_before,
        cost_after, rate_version, dry_run.
    """
    db = _get_db()
    where = ""
    params: list = []
    if days is not None:
        cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        where = "WHERE run_time >= ?"
        params = [cutoff]

    rows = db.execute(
        f"""SELECT id, job_id, run_time, input_tokens, output_tokens,
                   cache_read_tokens, cache_write_tokens, estimated_cost_usd,
                   no_agent, status, rate_version
            FROM cron_runs {where}""",
        params,
    ).fetchall()

    scanned = 0
    repriceable = 0
    updated = 0
    cost_before = 0.0
    cost_after = 0.0
    for r in rows:
        scanned += 1
        if r["no_agent"] or (r["status"] == "ok" and not (r["input_tokens"] or r["output_tokens"])):
            continue  # zero-cost run; nothing to re-price
        # Only re-price rows not already at the current version, and rows
        # whose stored cost is inconsistent with current rates.
        if r["rate_version"] == RATE_VERSION and r["estimated_cost_usd"] > 0:
            continue
        repriceable += 1
        run_dt = _parse_run_time(r["run_time"])
        new_cost = _compute_cost(r["input_tokens"], r["output_tokens"],
                                 r["cache_read_tokens"], r["cache_write_tokens"], run_dt)
        cost_before += float(r["estimated_cost_usd"] or 0.0)
        cost_after += new_cost
        if not dry_run:
            db.execute(
                "UPDATE cron_runs SET estimated_cost_usd = ?, rate_version = ? WHERE id = ?",
                (new_cost, RATE_VERSION, r["id"]),
            )
            updated += 1
    if not dry_run:
        db.commit()

    return {
        "rows_scanned": scanned,
        "rows_repriceable": repriceable,
        "rows_updated": updated,
        "cost_before": round(cost_before, 6),
        "cost_after": round(cost_after, 6),
        "delta_usd": round(cost_after - cost_before, 6),
        "rate_version": RATE_VERSION,
        "dry_run": dry_run,
    }


def _parse_run_time(run_time: str) -> datetime:
    """Parse 'YYYY-MM-DDTHH:MM:SSZ' (UTC) into a naive-UTC datetime."""
    try:
        return datetime.fromisoformat(run_time.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def get_run_stats(
    job_id: Optional[str] = None,
    *,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Get run cost records. If job_id is None, returns latest runs across all jobs.

    Returns records ordered by run_time descending.
    """
    try:
        db = _get_db()
        if job_id:
            rows = db.execute(
                """SELECT * FROM cron_runs WHERE job_id = ?
                   ORDER BY run_time DESC LIMIT ?""",
                (job_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT * FROM cron_runs
                   ORDER BY run_time DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("Failed to query cron cost store: %s", e)
        return []


def get_aggregate_stats(job_id: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate cost stats. If job_id=None, returns totals across all jobs.

    Returns:
        Dict with: total_runs, total_input_tokens, total_output_tokens,
        total_cache_read, total_cache_write, total_api_calls, total_cost_usd,
        per_model: {model_name: {runs, cost}}, per_job: {job_id: ...}
    """
    result: Dict[str, Any] = {
        "total_runs": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_write_tokens": 0,
        "total_api_calls": 0,
        "total_cost_usd": 0.0,
        "per_model": {},
        "per_job": {},
    }
    try:
        db = _get_db()
        where = "WHERE job_id = ?" if job_id else ""
        params = (job_id,) if job_id else ()

        # Overall totals
        row = db.execute(
            f"""SELECT
                COUNT(*) as total_runs,
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
                COALESCE(SUM(cache_write_tokens), 0) as total_cache_write_tokens,
                COALESCE(SUM(api_calls), 0) as total_api_calls,
                COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost_usd
            FROM cron_runs {where}""",
            params,
        ).fetchone()
        if row:
            result["total_runs"] = row["total_runs"]
            result["total_input_tokens"] = row["total_input_tokens"]
            result["total_output_tokens"] = row["total_output_tokens"]
            result["total_cache_read_tokens"] = row["total_cache_read_tokens"]
            result["total_cache_write_tokens"] = row["total_cache_write_tokens"]
            result["total_api_calls"] = row["total_api_calls"]
            result["total_cost_usd"] = float(row["total_cost_usd"])

        # Per-model breakdown
        model_rows = db.execute(
            f"""SELECT
                COALESCE(model, 'unknown') as model,
                COUNT(*) as runs,
                COALESCE(SUM(estimated_cost_usd), 0.0) as cost
            FROM cron_runs {where}
            GROUP BY model
            ORDER BY cost DESC""",
            params,
        ).fetchall()
        for r in model_rows:
            result["per_model"][r["model"]] = {
                "runs": r["runs"],
                "cost": float(r["cost"]),
            }

        # Per-job breakdown (only when no specific job_id filter)
        if not job_id:
            job_rows = db.execute(
                """SELECT
                    job_id,
                    COUNT(*) as runs,
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    COALESCE(SUM(cache_read_tokens), 0) as cache_read_tokens,
                    COALESCE(SUM(estimated_cost_usd), 0.0) as cost
                FROM cron_runs
                GROUP BY job_id
                ORDER BY cost DESC""",
            ).fetchall()
            for r in job_rows:
                result["per_job"][r["job_id"]] = {
                    "runs": r["runs"],
                    "input_tokens": r["input_tokens"],
                    "output_tokens": r["output_tokens"],
                    "cache_read_tokens": r["cache_read_tokens"],
                    "cost": float(r["cost"]),
                }

    except Exception as e:
        logger.debug("Failed to aggregate cron cost stats: %s", e)

    return result


def get_latest_run(job_id: str) -> Optional[Dict[str, Any]]:
    """Get the most recent run record for a job."""
    rows = get_run_stats(job_id, limit=1)
    return rows[0] if rows else None


def main(argv: Optional[List[str]] = None) -> int:
    """Standalone CLI for maintenance ops.

    Usage:
        cost_store.py --reprice [--days N] [--dry-run]
    """
    import argparse
    ap = argparse.ArgumentParser(description="Cron cost store maintenance (O1-S1)")
    ap.add_argument("--reprice", action="store_true",
                    help="Re-price recorded runs at current rates (rate-version stamp)")
    ap.add_argument("--days", type=int, default=None,
                    help="Only re-price runs newer than N days (default: all)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute new costs without writing")
    args = ap.parse_args(argv)

    if args.reprice:
        result = reprice_runs(days=args.days, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
