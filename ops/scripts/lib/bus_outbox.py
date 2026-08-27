#!/usr/bin/env python3
"""bus_outbox — enterprise-grade client-side retry for the Agent Bus.

When the bus is unreachable, `bus_send()` would return None and the
message would be silently lost. This module makes bus delivery durable:

  enqueue(queue, message_body)
      Write the message to ~/.hermes-cortex/bus-retry/ atomically.
      Returns {"queued": true, "outbox_file": <path>} or raises.

  sweep(now=None)
      Re-send queued messages with exponential backoff + jitter,
      dedup against already-pending queue messages (canonical rule in
      cortex_bus.bus_find_duplicate), quarantine poison-pill messages
      (corrupt / max attempts). Returns a result dict; prints nothing
      (watchdog pattern — the cron delivers only when something happened).

  main()  — CLI entry; the agent-bus-retry-sweep cron calls this module
            DIRECTLY (script=lib/bus_outbox.py). No wrapper script, no
            sys.path hack — this file sits in lib/ beside cortex_bus.py.

Design (enterprise-grade):
  - Atomic writes: tmp file + fsync + os.replace + dir fsync — a
    crash never leaves a torn retry file.
  - Deterministic filenames: <queue>-<sha1>.json where the hash covers
    queue+correlation_id+body — re-enqueueing the same message
    overwrites instead of duplicating. bus_send never mutates the
    caller's dict, so the pristine message is what gets hashed.
  - Backoff: min(2^attempts, 1024) minutes +- 20% jitter. Attempts
    counts FAILED sweeps; a fresh file is retried on the first sweep
    (>=1 minute old).
  - Dedup on resend: peek the target queue first; if an identical
    message (same correlation_id OR same subject+body) is already
    pending, delete the file without re-sending. This closes the
    at-least-once hazard where a send landed but its response was lost.
  - Poison-pill quarantine: corrupt JSON or attempts >= MAX_ATTEMPTS
    moves the file to bus-retry/quarantine/ — it stops retrying forever.
  - Concurrency: the sweep holds an flock; cron and manual sweeps can
    never race.
  - Config via env: CORTEX_BUS_RETRY_DIR overrides the default dir
    (tests + non-default installs); CORTEX_BUS_NO_OUTBOX=1 disables
    the fallback in bus_send (hard-fail to None).
"""
import fcntl
import hashlib
import json
import logging
import os
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path

from cortex_bus import bus_peek, bus_send, bus_find_duplicate  # noqa: E402

log = logging.getLogger("bus_outbox")

DEFAULT_RETRY_DIR = Path.home() / ".hermes-cortex" / "bus-retry"
RETRY_DIR = Path(os.environ.get("CORTEX_BUS_RETRY_DIR", DEFAULT_RETRY_DIR))
QUARANTINE_DIR = RETRY_DIR / "quarantine"
LOCK_FILE = RETRY_DIR / ".sweep.lock"

MAX_ATTEMPTS = 12
BACKOFF_BASE_MINUTES = 1          # 2^attempts minutes, attempts=0 -> 1 min
BACKOFF_CAP_MINUTES = 1024        # ~17h cap
JITTER = 0.20                     # +-20%


def _sha1(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode("utf-8", errors="replace"))
    return h.hexdigest()[:12]


def _filename(queue: str, message_body: dict) -> str:
    """Content-derived name: re-enqueueing the same message deterministically
    overwrites (write-time dedup), regardless of wall-clock timing."""
    corr = str(message_body.get("correlation_id") or "")
    body_text = json.dumps(message_body, sort_keys=True, ensure_ascii=False)
    digest = _sha1(queue, corr, body_text)
    return f"{queue}-{digest}.json"


def enqueue(queue: str, message_body: dict) -> dict:
    """Durably queue a message for later delivery.

    Atomic: write to a tmp file, fsync, os.replace, fsync the dir.
    Deterministic name: re-enqueueing the same message overwrites.
    """
    RETRY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "queue": queue,
        "message_body": message_body,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "attempts": 0,
        "last_error": "",
    }
    path = RETRY_DIR / _filename(queue, message_body)
    tmp = path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    # fsync the directory so the rename itself is durable
    try:
        dfd = os.open(str(RETRY_DIR), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass  # dir fsync is best-effort on some filesystems
    log.info("queued %s -> %s (%s)", queue, path.name,
             message_body.get("correlation_id") or "no-corr")
    return {"queued": True, "outbox_file": str(path)}


def _backoff_minutes(attempts: int) -> float:
    base = min(BACKOFF_BASE_MINUTES * (2 ** attempts), BACKOFF_CAP_MINUTES)
    jitter = 1.0 + random.uniform(-JITTER, JITTER)
    return base * jitter


def _quarantine(path: Path, reason: str) -> None:
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    dest = QUARANTINE_DIR / path.name
    os.replace(str(path), str(dest))
    log.warning("QUARANTINED %s: %s", path.name, reason)


def sweep(now: float | None = None) -> dict:
    """Re-send queued messages. Returns a result dict (never raises).

    Safe to run concurrently: holds an flock on LOCK_FILE for the
    whole pass. The cron (every 15 min) and a manual run can't race.
    """
    now = now if now is not None else time.time()
    result = {"scanned": 0, "sent": 0, "deduped": 0, "quarantined": 0,
              "backoff": 0, "failed": 0, "errors": []}

    RETRY_DIR.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.info("sweep skipped: another sweep holds the lock")
        result["errors"].append("lock held by another sweep")
        return result
    try:
        for path in sorted(RETRY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime):
            result["scanned"] += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                attempts = int(payload.get("attempts", 0))
            except (ValueError, OSError, json.JSONDecodeError) as e:
                _quarantine(path, f"corrupt retry file: {e}")
                result["quarantined"] += 1
                continue

            queue = payload.get("queue")
            message_body = payload.get("message_body")
            if not queue or not isinstance(message_body, dict):
                _quarantine(path, "missing queue or message_body")
                result["quarantined"] += 1
                continue

            # Backoff: only retry files old enough for this attempt count
            age_minutes = (now - path.stat().st_mtime) / 60.0
            if age_minutes < _backoff_minutes(attempts):
                result["backoff"] += 1
                continue

            # Dedup: if an identical message is already pending, the
            # delivery already happened (or another path queued it) —
            # drop the retry file.
            try:
                pending = bus_peek(queue, limit=50)
            except Exception as e:  # noqa: BLE001 — peek failure = treat as busy
                result["failed"] += 1
                result["errors"].append(f"peek {queue}: {e}")
                continue
            if bus_find_duplicate(
                pending or [],
                message_body.get("subject"),
                message_body.get("body"),
                message_body.get("correlation_id") or "",
            ):
                path.unlink(missing_ok=True)
                result["deduped"] += 1
                continue

            try:
                outcome = bus_send(queue, message_body)
            except Exception as e:  # noqa: BLE001 — never let one file kill the sweep
                outcome = None
            if outcome is not None and outcome.get("queued") is not True:
                path.unlink(missing_ok=True)
                result["sent"] += 1
                continue
            # outcome is None (bus down) or re-queued (bus still down):
            # bump attempts, possibly quarantine.
            attempts += 1
            if attempts >= MAX_ATTEMPTS:
                _quarantine(path, f"max attempts ({MAX_ATTEMPTS}) reached")
                result["quarantined"] += 1
                continue
            payload["attempts"] = attempts
            payload["last_error"] = "bus unreachable" if outcome is None else "re-queued"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(str(tmp), str(path))
            result["failed"] += 1
    finally:
        os.close(lock_fd)

    return result


def main() -> int:
    """CLI entry for the cron: prints ONLY when something happened.

    Watchdog pattern: empty output + exit 0 = silent tick. A
    quarantine or repeated failure prints one line per event, which
    the cron delivers.
    """
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    r = sweep()
    lines = []
    if r["quarantined"]:
        lines.append(f"bus-outbox: {r['quarantined']} message(s) QUARANTINED (see {QUARANTINE_DIR})")
    if r["failed"] and r["failed"] >= 3:
        lines.append(f"bus-outbox: {r['failed']} retries failed, bus may be down")
    for line in lines:
        print(line)
    # exit 1 only on quarantine (needs attention); transient failures
    # are expected while the bus is down and the cron keeps sweeping.
    return 1 if r["quarantined"] else 0


if __name__ == "__main__":
    sys.exit(main())
