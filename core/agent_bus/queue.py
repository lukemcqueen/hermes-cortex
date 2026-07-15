"""
Postgres-native message queue client.

Connects to the Hermes Cortex Postgres instance and provides
send/read/archive operations on bus queues.
"""

import json
import os
from typing import Any, Optional
from pathlib import Path


class NotAvailableError(RuntimeError):
    """Raised when bus is accessed on a worker agent (no PG creds)."""


def _load_config() -> dict:
    """Load bus Postgres config from environment or .env file.
    
    Only the inbox server (Moses/Esther) has these env vars.
    Worker agents get NotAvailableError.
    """
    # Check env vars first
    config = {
        "host": os.environ.get("CORTEX_BUS_PG_HOST", ""),
        "port": int(os.environ.get("CORTEX_BUS_PG_PORT", "15432")),
        "db": os.environ.get("CORTEX_BUS_PG_DB", "gbrain"),
        "user": os.environ.get("CORTEX_BUS_PG_USER", ""),
        "password": os.environ.get("CORTEX_BUS_PG_PASS", ""),
    }

    # Fall back to .env
    if not config["user"]:
        env_file = Path.home() / "hermes-cortex" / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                if k == "CORTEX_BUS_PG_HOST" and not config["host"]:
                    config["host"] = v
                elif k == "CORTEX_BUS_PG_PORT" and not config["port"]:
                    config["port"] = int(v)
                elif k == "CORTEX_BUS_PG_USER" and not config["user"]:
                    config["user"] = v
                elif k == "CORTEX_BUS_PG_PASS" and not config["password"]:
                    config["password"] = v

    # Fall back to gbrain Postgres (same instance)
    if not config["user"]:
        config["user"] = os.environ.get("POSTGRES_USER", "gbrain")
        config["password"] = os.environ.get("POSTGRES_PASSWORD", "")

    return config


def _connect():
    """Create a raw psycopg connection to the bus Postgres.
    
    Imports psycopg lazily so this module can be imported without it.
    """
    try:
        import psycopg
    except ImportError:
        raise ImportError(
            "psycopg package required. Install: pip install psycopg[binary]"
        )

    config = _load_config()
    if not config["user"] or not config["password"]:
        raise NotAvailableError(
            "Bus requires Postgres credentials. "
            "Set CORTEX_BUS_PG_USER and CORTEX_BUS_PG_PASS env vars, "
            "or run on the inbox server (Moses/Esther)."
        )

    return psycopg.connect(
        host=config["host"],
        port=config["port"],
        dbname=config["db"],
        user=config["user"],
        password=config["password"],
    )


class BusClient:
    """Synchronous client for the Hermes Cortex Agent Bus."""

    def __init__(self, conn=None):
        self._conn = conn

    def _ensure_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = _connect()
        else:
            # Recover from broken transactions
            try:
                if self._conn.info.transaction_status is not None:
                    from psycopg.pq import TransactionStatus
                    ts = self._conn.info.transaction_status
                    if ts in (TransactionStatus.INERROR, TransactionStatus.UNKNOWN):
                        self._conn.rollback()
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    self._conn = _connect()

    def send(
        self,
        queue: str,
        body: dict,
        priority: int = 0,
        correlation_id: Optional[str] = None,
        max_retries: Optional[int] = None,
    ) -> str:
        """Send a message to a queue."""
        self._ensure_conn()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT bus.send(%s, %s, %s, %s, %s)",
                (queue, json.dumps(body), priority, correlation_id, max_retries),
            )
            msg_id = cur.fetchone()[0]
            self._conn.commit()
            return msg_id

    def read(self, queue: str, vt: int = 60) -> Optional[dict]:
        """Read a message from a queue.
        
        Args:
            queue: Queue name (e.g. 'inbox_moses')
            vt: Visibility timeout in seconds. Message reappears after this
                if not archived.
        
        Returns:
            Message dict with keys: msg_id, queue, body, priority, retry_count,
            max_retries, from_dlq, enqueued_at, timeout_at
            Or None if queue is empty.
        """
        self._ensure_conn()
        with self._conn.cursor() as cur:
            cur.execute("SELECT bus.read(%s, %s)", (queue, vt))
            row = cur.fetchone()
            self._conn.commit()
            if row and row[0]:
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return None

    def archive(self, queue: str, msg_id: str, archived_by: str = "system") -> bool:
        """Archive a processed message (moves to archive table)."""
        self._ensure_conn()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT bus.archive(%s, %s::uuid, %s)",
                (queue, msg_id, archived_by),
            )
            result = cur.fetchone()[0]
            self._conn.commit()
            return bool(result)

    def requeue(self, queue: str, msg_id: str, error: Optional[str] = None) -> bool:
        """Re-queue a failed message (increments retry count)."""
        self._ensure_conn()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT bus.requeue(%s, %s::uuid, %s)",
                (queue, msg_id, error),
            )
            result = cur.fetchone()[0]
            self._conn.commit()
            return bool(result)

    def delete(self, queue: str, msg_id: str) -> bool:
        """Delete a message from a queue."""
        self._ensure_conn()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT bus.delete(%s, %s::uuid)",
                (queue, msg_id),
            )
            result = cur.fetchone()[0]
            self._conn.commit()
            return bool(result)

    def depth(self, queue: str) -> int:
        """Get the number of pending messages in a queue."""
        self._ensure_conn()
        with self._conn.cursor() as cur:
            cur.execute("SELECT bus.depth(%s)", (queue,))
            return cur.fetchone()[0]

    def list_queues(self) -> list[dict]:
        """List all queues with depth and metadata."""
        self._ensure_conn()
        with self._conn.cursor() as cur:
            cur.execute("SELECT bus.list_queues()")
            row = cur.fetchone()
            if row and row[0]:
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return []

    def create_queues_for_agent(self, agent_name: str, max_retries: int = 3):
        """Idempotently create inbox + DLQ queues for an agent."""
        self._ensure_conn()
        with self._conn.cursor() as cur:
            main_queue = f"inbox_{agent_name}"
            dlq_queue = f"inbox_{agent_name}_dlq"
            
            # Create main queue
            cur.execute(
                "INSERT INTO bus.queues (name, max_retries) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                (main_queue, max_retries),
            )
            # Create DLQ
            cur.execute(
                "INSERT INTO bus.queues (name, max_retries, is_dlq, parent_queue) "
                "VALUES (%s, %s, true, %s) ON CONFLICT (name) DO NOTHING",
                (dlq_queue, max_retries, main_queue),
            )
            self._conn.commit()

    def close(self):
        """Close the connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


_client_cache: Optional[BusClient] = None


def get_queue() -> BusClient:
    """Get a configured BusClient.
    
    Reuses a cached connection within the same process.
    Only callable on machines with Postgres access (Moses/Esther).
    Worker agents get NotAvailableError.
    
    Usage:
        bus = get_queue()
        bus.send("inbox_moses", {"from": "test", "body": "hello"})
    """
    global _client_cache
    if _client_cache is None:
        _client_cache = BusClient()
    return _client_cache
