#!/usr/bin/env python3
"""bot_locks.py — per-bot advisory locks for the messaging gateway.

SRE finding (party 2026-08-24): one daemon does NOT solve the 409 class —
ANY second poller (old adapter during cutover, second gateway on another
server, a stray bridge) gets 409 and the bot goes silently dark. The fix
is exclusive per-bot ownership at the DATABASE: `pg_try_advisory_lock`
held for the poller's lifetime. A gateway that cannot acquire the lock
stands down (bot stays unowned/standby) instead of polling.

This one mechanism covers:
  - 409 avoidance: only the lock holder polls the bot
  - migration cutover: old adapter can't poll while the gateway holds it
  - multi-server: active-passive via the same lock (standby waits)

Usage (inside msg-gateway):
    from bot_locks import BotLock
    with BotLock(pg_conn_factory, bot_id_hash) as acquired:
        if not acquired:
            stand down (bot unowned) — do NOT poll
        else:
            poll the bot for the whole session
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator, Optional


def _connect():
    """Reuse the bus core's psycopg connection (same seam as queue.py)."""
    import importlib.util
    from pathlib import Path
    # The bus core lives at core/cortex_bus/queue.py (repo) or
    # ~/.hermes-cortex/queue.py (deployed). Try the deployed first, then
    # the repo relative path.
    candidates = [
        Path.home() / ".hermes-cortex" / "queue.py",
        Path(__file__).resolve().parent.parent.parent
        / "core" / "cortex_bus" / "queue.py",
    ]
    for path in candidates:
        if path.exists():
            spec = importlib.util.spec_from_file_location("cortex_bus_queue", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod._connect()
    raise RuntimeError("cortex_bus queue.py not found (bus core missing)")


def _try_lock(conn, key: int) -> bool:
    """pg_try_advisory_lock — non-blocking, session-scoped (auto-released
    when the connection closes, so a crashed gateway never leaks a lock)."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (key,))
        return bool(cur.fetchone()[0])


def _unlock(conn, key: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", (key,))


@contextmanager
def BotLock(conn_factory: Callable[[], object], key: int) -> Iterator[bool]:
    """Acquire the per-bot advisory lock for this session.

    Yields True if acquired (caller owns the bot), False if another
    holder owns it (caller stands down — must NOT poll).
    """
    conn = conn_factory()
    try:
        acquired = _try_lock(conn, key)
        yield acquired
    finally:
        if acquired:
            try:
                _unlock(conn, key)
            except Exception:
                pass  # connection close releases session locks anyway
        try:
            conn.close()
        except Exception:
            pass


def bot_key(bot_token_ref: str, channel: str) -> int:
    """Deterministic advisory-lock key for a bot (token_ref + channel)."""
    import hashlib
    digest = hashlib.sha256(f"{channel}:{bot_token_ref}".encode()).digest()
    # pg advisory locks take a 64-bit bigint — take the first 8 bytes
    return int.from_bytes(digest[:8], "big", signed=True)
