"""
Cron job cost tracking store.

SQLite-backed store for per-run token usage and estimated cost.
Stored alongside cron output under ~/.hermes/cron/cron-costs.db.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cron.jobs import CRON_DIR, _secure_file

logger = logging.getLogger(__name__)

# Lazy-init to avoid import-time filesystem dependency
_db: Optional[sqlite3.Connection] = None
_db_lock = threading.Lock()
_DB_PATH = CRON_DIR / "cron-costs.db"


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
                status        TEXT DEFAULT 'ok'
            );
            CREATE INDEX IF NOT EXISTS idx_cron_runs_job_id ON cron_runs(job_id);
            CREATE INDEX IF NOT EXISTS idx_cron_runs_run_time ON cron_runs(run_time);
        """)
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
                estimated_cost_usd, model, provider, no_agent, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            ),
        )
        db.commit()
    except Exception as e:
        logger.warning("Failed to record cron cost for job '%s': %s", job_id, e)


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
