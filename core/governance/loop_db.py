"""
Loop Governance Database — persistent data capture for self-improvement.

Stores every loop cycle's scores, decisions, and content snapshots in SQLite.
Also writes JSON event logs for streaming backup/portability.

Schema (auto-created on first use):
  - loop_cycles:     Every cycle's scores + decisions + content hashes
  - content_assets:  Content-addressable store (deduplicates code/spec/test text)
  - config_history:  Config change log for rollback

Usage:
    from loop_db import LoopDB

    db = LoopDB("~/.hermes-cortex/data/loop-governance.db")
    db.log_cycle(task_id="task-1", cycle_num=1, completeness=8.0, ...)
    stats = db.get_summary_stats()
    db.close()
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Advisory lock (inter-process) ────────────────────────────
_ADVISORY_LOCK_AVAILABLE = False
try:
    import fcntl as _flock_mod
    _ADVISORY_LOCK_AVAILABLE = True
except ImportError:
    _flock_mod = None  # Windows — no advisory locking via fcntl


def content_hash(text: str) -> str:
    """Return SHA-256 hex digest of text (content-addressable key)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


DEFAULT_DB_PATH = os.path.expanduser("~/.hermes-cortex/data/loop-governance.db")
EVENTS_DIR = os.path.expanduser("~/.hermes-cortex/data/loop-events")


class LoopDB:
    """Persistent store for loop governance data."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        if db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            # Lock file for inter-process advisory locking
            self._lock_path = db_path + ".lock"
            self._lock_fd = None
        else:
            self._lock_path = None
            self._lock_fd = None
        self._create_schema()

    def _lock(self) -> None:
        """Acquire an inter-process advisory lock. Blocks if another process holds it.
        Uses fcntl.flock on POSIX; no-op on Windows."""
        if not _ADVISORY_LOCK_AVAILABLE or not self._lock_path:
            return
        try:
            self._lock_fd = open(self._lock_path, "w")
            _flock_mod.flock(self._lock_fd, _flock_mod.LOCK_EX)
        except Exception:
            self._lock_fd = None

    def _unlock(self) -> None:
        """Release the advisory lock."""
        if self._lock_fd is not None:
            try:
                _flock_mod.flock(self._lock_fd, _flock_mod.LOCK_UN)
                self._lock_fd.close()
            except Exception:
                pass
            self._lock_fd = None

    def _create_schema(self):
        """Create tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS loop_cycles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
                task_id         TEXT NOT NULL,
                cycle_num       INTEGER NOT NULL,
                spec_hash       TEXT,
                code_hash       TEXT,
                test_output_hash TEXT,
                completeness    REAL NOT NULL,
                quality         REAL NOT NULL,
                progress        REAL NOT NULL,
                composite       REAL NOT NULL,
                no_progress     INTEGER NOT NULL DEFAULT 0,
                decision        TEXT NOT NULL,
                user_overrode   INTEGER,
                outcome_note    TEXT,
                schema_version  INTEGER DEFAULT 1,
                model_name      TEXT DEFAULT 'nomic-embed-text:v1.5'
            );

            CREATE TABLE IF NOT EXISTS content_assets (
                hash    TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                type    TEXT NOT NULL,
                created TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS config_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                applied_at      TEXT NOT NULL DEFAULT (datetime('now')),
                config_json     TEXT NOT NULL,
                diff_from_previous TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_cycles_task
                ON loop_cycles(task_id);
            CREATE INDEX IF NOT EXISTS idx_cycles_timestamp
                ON loop_cycles(timestamp);
            CREATE INDEX IF NOT EXISTS idx_cycles_decision
                ON loop_cycles(decision);

            CREATE TABLE IF NOT EXISTS task_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
                task_id     TEXT NOT NULL,
                agent       TEXT,
                event_type  TEXT NOT NULL,
                from_state  TEXT,
                to_state    TEXT,
                detail      TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_task_events_task
                ON task_events(task_id);
        """)
        self.conn.commit()

    # ── Write ────────────────────────────────────────────────────────────────

    def log_cycle(self, task_id: str, cycle_num: int, completeness: float,
                  quality: float, progress: float, composite: float,
                  no_progress: bool, decision: str,
                  spec_hash: str = None, code_hash: str = None,
                  test_output_hash: str = None,
                  model_name: str = "nomic-embed-text:v1.5") -> int:
        """Log a scored cycle and return the row ID.

        Auto-accepts cycles with STOP decision (completed, composite >= 8.0)
        by setting user_overrode=0. LOOP/MOVE_ON/no_progress cycles stay
        NULL for human review via feedback_accept/feedback_override.
        """
        # Auto-accept STOP decisions — the LLM judge confirmed completion.
        # LOOP/MOVE_ON/no_progress need human attention.
        decision_upper = (decision or "").strip().upper()
        user_overrode = 0 if decision_upper.startswith("STOP") else None

        self._lock()
        try:
            cur = self.conn.execute("""\
            INSERT INTO loop_cycles
                (task_id, cycle_num, spec_hash, code_hash, test_output_hash,
                 completeness, quality, progress, composite, no_progress,
                 decision, model_name, user_overrode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (task_id, cycle_num, spec_hash, code_hash, test_output_hash,
              completeness, quality, progress, composite,
              1 if no_progress else 0, decision, model_name, user_overrode))
            self.conn.commit()

            # Write JSON event
            self._write_event(cur.lastrowid, task_id, cycle_num, completeness,
                              quality, progress, composite, no_progress, decision)

            return cur.lastrowid
        finally:
            self._unlock()

    def log_cycle_with_content(self, task_id: str, cycle_num: int,
                                spec_text: str, code_text: str,
                                test_output: str,
                                completeness: float, quality: float,
                                progress: float, composite: float,
                                no_progress: bool, decision: str) -> int:
        """Store content and log cycle in one call."""
        spec_hash = None
        code_hash = None
        test_hash = None

        if spec_text:
            spec_hash = content_hash(spec_text)
            self.store_content(spec_hash, self.sanitize_code(spec_text), "spec")
        if code_text:
            code_hash = content_hash(code_text)
            self.store_content(code_hash, self.sanitize_code(code_text), "code")
        if test_output:
            test_hash = content_hash(test_output)
            self.store_content(test_hash, test_output, "test_output")

        return self.log_cycle(
            task_id=task_id, cycle_num=cycle_num,
            spec_hash=spec_hash, code_hash=code_hash,
            test_output_hash=test_hash,
            completeness=completeness, quality=quality,
            progress=progress, composite=composite,
            no_progress=no_progress, decision=decision,
        )

    def store_content(self, hash_key: str, content: str, type_: str):
        """Store content in the content-addressable store (idempotent)."""
        self.conn.execute("""
            INSERT OR IGNORE INTO content_assets (hash, content, type)
            VALUES (?, ?, ?)
        """, (hash_key, content, type_))
        self.conn.commit()

    def record_user_outcome(self, cycle_id: int, accepted: bool, note: str = ""):
        """Record whether the user accepted or overrode the loop decision."""
        self.conn.execute("""
            UPDATE loop_cycles
            SET user_overrode = ?, outcome_note = ?
            WHERE id = ?
        """, (0 if accepted else 1, note, cycle_id))
        self.conn.commit()

    def record_config_change(self, config_json: str, diff: str = ""):
        """Log a config change for rollback tracking."""
        self.conn.execute("""
            INSERT INTO config_history (config_json, diff_from_previous)
            VALUES (?, ?)
        """, (config_json, diff))
        self.conn.commit()

    # ── Task Events ──────────────────────────────────────────────────────────

    def log_task_event(self, task_id: str, event_type: str,
                       agent: str = "", from_state: str = "",
                       to_state: str = "", detail: str = "") -> int:
        """Log a task event (state transition, issue, interruption, etc.).

        Returns the row ID of the inserted event.
        """
        self._lock()
        try:
            cur = self.conn.execute("""
                INSERT INTO task_events (task_id, agent, event_type, from_state, to_state, detail)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, agent, event_type, from_state, to_state, detail))
            self.conn.commit()
            return cur.lastrowid or 0
        finally:
            self._unlock()

    def get_task_events(self, task_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get events for a task, newest first."""
        rows = self.conn.execute("""
            SELECT * FROM task_events
            WHERE task_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (task_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_cycle(self, cycle_id: int) -> Optional[Dict[str, Any]]:
        """Get a single cycle by ID."""
        row = self.conn.execute(
            "SELECT * FROM loop_cycles WHERE id = ?", (cycle_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_cycles_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all cycles for a task, ordered by cycle_num."""
        rows = self.conn.execute(
            "SELECT * FROM loop_cycles WHERE task_id = ? ORDER BY cycle_num",
            (task_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_cycles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent N cycles."""
        rows = self.conn.execute(
            "SELECT * FROM loop_cycles ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_no_progress_streak(self, task_id: str) -> int:
        """Return count of consecutive no-progress cycles at the end of a task."""
        rows = self.conn.execute("""
            SELECT no_progress FROM loop_cycles
            WHERE task_id = ?
            ORDER BY cycle_num DESC
        """, (task_id,)).fetchall()
        streak = 0
        for r in rows:
            if r["no_progress"]:
                streak += 1
            else:
                break
        return streak

    def get_content(self, hash_key: str) -> Optional[str]:
        """Retrieve content by hash."""
        row = self.conn.execute(
            "SELECT content FROM content_assets WHERE hash = ?", (hash_key,)
        ).fetchone()
        return row["content"] if row else None

    def get_summary_stats(self) -> Dict[str, Any]:
        """Aggregate statistics across all cycles."""
        stats = self.conn.execute("""
            SELECT
                COUNT(*) AS total_cycles,
                COALESCE(AVG(completeness), 0) AS avg_completeness,
                COALESCE(AVG(quality), 0) AS avg_quality,
                COALESCE(AVG(progress), 0) AS avg_progress,
                COALESCE(AVG(composite), 0) AS avg_composite,
                SUM(CASE WHEN decision = 'STOP ✓' THEN 1 ELSE 0 END) AS stop_count,
                SUM(CASE WHEN decision LIKE 'LOOP%' THEN 1 ELSE 0 END) AS loop_count,
                SUM(CASE WHEN decision LIKE 'MOVE ON%' THEN 1 ELSE 0 END) AS move_on_count,
                SUM(CASE WHEN decision LIKE 'STOP ✗%' THEN 1 ELSE 0 END) AS hard_fail_count,
                SUM(CASE WHEN no_progress = 1 THEN 1 ELSE 0 END) AS no_progress_count,
                SUM(CASE WHEN user_overrode IS NOT NULL THEN 1 ELSE 0 END) AS user_feedback_count
            FROM loop_cycles
        """).fetchone()
        return dict(stats)

    def get_decision_accuracy(self) -> Dict[str, Any]:
        """Compare decisions against user feedback. Requires user_overrode to be set."""
        rows = self.conn.execute("""
            SELECT decision, user_overrode, COUNT(*) AS count
            FROM loop_cycles
            WHERE user_overrode IS NOT NULL
            GROUP BY decision, user_overrode
        """).fetchall()
        return {
            "total_feedback": sum(r["count"] for r in rows),
            "breakdown": [dict(r) for r in rows],
        }

    # ── Utilities ────────────────────────────────────────────────────────────

    def vacuum_old_cycles(self, days: int = 90, archive_dir: str = None) -> dict:
        """Archive cycles older than N days to JSON and delete from SQLite.

        Args:
            days: Age threshold in days (default 90).
            archive_dir: Directory for JSON archives (default: ~/.hermes-cortex/data/loop-archive/).

        Returns:
            dict with count of archived cycles, archive path, and DB size before/after.
        """
        archive_dir = archive_dir or os.path.expanduser("~/.hermes-cortex/data/loop-archive")
        os.makedirs(archive_dir, exist_ok=True)

        # Get size before
        before = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0

        # Find old cycles
        old_cycles = self.conn.execute("""
            SELECT * FROM loop_cycles
            WHERE timestamp < datetime('now', '-' || ? || ' days')
            ORDER BY id
        """, (days,)).fetchall()

        if not old_cycles:
            return {"archived": 0, "archive_path": "", "before_bytes": before, "after_bytes": before}

        # Archive to JSON
        archive_date = datetime.now(timezone.utc).strftime("%Y-%m")
        archive_path = os.path.join(archive_dir, f"cycles-pre-{archive_date}.jsonl")
        ids = []
        with open(archive_path, "a") as f:
            for row in old_cycles:
                f.write(json.dumps(dict(row), default=str) + "\n")
                ids.append(row["id"])

        # Delete from SQLite
        ids_str = ",".join(str(i) for i in ids)
        self.conn.execute(f"DELETE FROM loop_cycles WHERE id IN ({ids_str})")
        self.conn.commit()
        self.conn.execute("VACUUM")
        if self.db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")  # restore WAL mode after VACUUM

        after = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        return {
            "archived": len(old_cycles),
            "archive_path": archive_path,
            "before_bytes": before,
            "after_bytes": after,
            "saved_bytes": before - after,
        }

    @staticmethod
    def sanitize_code(code: str) -> str:
        """Remove potential secrets from code before storage.

        Strips:
          - API keys, tokens, passwords in assignments
          - Connection strings with credentials
          - Private key blocks
        """
        # API keys / tokens / passwords in variable assignments
        sanitized = re.sub(
            r'(?i)(api_key|api_secret|token|password|secret|private_key)\s*[=:]\s*["\'][^"\']+["\']',
            r'\1 = "***REDACTED***"',
            code,
        )
        # Connection strings with credentials
        sanitized = re.sub(
            r'(?i)(postgresql|mysql|mongodb|redis|amqp|https?)://[^@]+@',
            r'\1://***:***@',
            sanitized,
        )
        # PEM private key blocks
        sanitized = re.sub(
            r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----.*?-----END\s+(RSA\s+)?PRIVATE\s+KEY-----',
            '-----BEGIN PRIVATE KEY-----\n***REDACTED***\n-----END PRIVATE KEY-----',
            sanitized,
            flags=re.DOTALL,
        )
        return sanitized

    def _write_event(self, cycle_id: int, task_id: str, cycle_num: int,
                     completeness: float, quality: float, progress: float,
                     composite: float, no_progress: bool, decision: str):
        """Write a JSON event to the events directory for streaming backup."""
        os.makedirs(EVENTS_DIR, exist_ok=True)
        event = {
            "event": "cycle_scored",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cycle_id": cycle_id,
            "task_id": task_id,
            "cycle_num": cycle_num,
            "scores": {
                "completeness": completeness,
                "quality": quality,
                "progress": progress,
                "composite": composite,
            },
            "no_progress": no_progress,
            "decision": decision,
        }
        # Append to daily file
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        event_path = os.path.join(EVENTS_DIR, f"{date_str}.jsonl")
        with open(event_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
