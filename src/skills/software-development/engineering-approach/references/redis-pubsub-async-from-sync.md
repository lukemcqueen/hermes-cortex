# Async Event Publishing from Sync FastAPI Endpoints via Redis Pub/Sub

Fire-and-forget Redis pub/sub events from synchronous FastAPI endpoint handlers when the withdrawal/revocation has already been committed to the DB. The event is a notification to downstream systems, not a transaction participant.

## Pattern

```python
def _publish_event(user_id: int, purpose: str, withdrawn_at: datetime, withdrawn_by: str | None = None) -> None:
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # No event loop in this thread (e.g. test threads, background workers)
        logger.warning("event_publish_skipped: no event loop")
        return

    try:
        coro = get_publisher().publish_event(
            user_id=user_id,
            purpose=purpose,
            withdrawn_at=withdrawn_at.isoformat(),
            withdrawn_by=withdrawn_by or "user",
        )
        if loop.is_running():
            asyncio.ensure_future(coro)
        else:
            loop.run_until_complete(coro)
    except Exception as exc:
        logger.warning("event_publish_failed", exc_info=exc)
```

## Order of Operations

1. **Commit the state change first** (DB commit)
2. Then publish the event (non-blocking on failure)
3. Then write the audit log (same DB session)

Never publish before the commit — downstream systems could read stale state.

## EventPublisher Class Structure

See `apps/api/services/events.py` for a complete implementation:

```python
class EventPublisher:
    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "")
        self._redis: redis.asyncio.Redis | None = None

    def _get_redis(self) -> redis.asyncio.Redis | None:
        """Lazy connection — returns None if redis_url is empty (tests/local dev)."""
        if self._redis is None and self._redis_url:
            self._redis = redis.asyncio.from_url(self._redis_url)
        return self._redis

    async def publish_consent_withdrawal(self, user_id: int, purpose: str, ...) -> bool:
        r = self._get_redis()
        if r is None:
            return False  # Silent fallback
        ...
```

Key design decisions:
- **Lazy connection** — Redis connection is established on first publish, not at import time
- **Silent fallback** — if `REDIS_URL` is empty (common in tests), publishing returns `False` without error
- **Channel naming** — use dot-namespaced channels like `consent:withdrawal` for easy subscription filtering
- **Event schema** — include `type` discriminator + `data` payload with ISO timestamps for downstream consumers

## Kafka vs Redis Pub/Sub — When Each Fits

| Criterion | Redis Pub/Sub | Kafka |
|-----------|---------------|-------|
| Latency requirement | ≤500ms | ≤50ms |
| Message durability | Not required (re-query DB if missed) | Required (replay from offset) |
| Consumer group scaling | Not needed (1-2 subscribers) | Needed (10+ consumers per group) |
| Monitoring/observability | Manual (pub/sub has no built-in acks) | Required (built-in offset tracking + lag) |

Redis Pub/Sub is correct for ACME consent withdrawal propagation because:
- The committed DB state is the source of truth — missed events are recovered by re-querying
- ≤500ms is well within Redis pub/sub capability
- Only 1-3 downstream systems need the notification

## Test Strategy

1. **Set `REDIS_URL=""` in test conftest** — prevents stale Redis connections across TestClient event loops
2. **Verify the event is NOT published** — the `EventPublisher._get_redis()` returns `None`, so `publish_*` returns `False` — test that the withdrawal still succeeds regardless
3. **Verify the audit log** — the event publishing is non-blocking; verify the real side effect (audit log entry) in the DB after the HTTP request

```python
def test_withdraw_graceful_when_redis_down(self, client: TestClient):
    self.setup_purpose(client, "usage_matching")
    resp = client.post("/api/v1/consents/withdraw/usage_matching")
    assert resp.status_code == 200
    assert resp.json()["status"] == "withdrawn"
```

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| `asyncio.get_event_loop()` raises `RuntimeError` in test threads | Catch `RuntimeError` and return gracefully — the event is non-critical |
| `asyncio.get_event_loop()` returns a closed loop | Use `loop.is_closed()` check before scheduling |
| `asyncio.ensure_future()` without holding a reference to the task | Store the task or use `asyncio.create_task()` (Python 3.7+) with error callback |
| Redis connection failure raises during publish | Wrap publish in try/except — log the warning, don't crash the request |
| Test uses same DB schema name as production (`acme_test` hardcoded) | Use `os.getenv("POSTGRES_PORT")` for port, derive DB name from that or a env variable — don't hardcode in the test fixture |
| `REDIS_URL` set to empty string in conftest blocks all Redis calls | Check for empty URL before attempting connection in `_get_redis()` |
| Multiple test files sharing the same engine import race for `pg_texample` extension creation | Use `CREATE EXTENSION IF NOT EXISTS` with `@event.listens_for(engine, "connect")` — idempotent and per-connection |
