---
version: 1.0.0
name: bus-client-resilience
category: devops
description: "Use when changing the bus client, outbox, mirror, or DLQ."
platforms: [linux]
---

# Bus Client Resilience — fail-fast, outbox, mirror

Class-level procedure for hardening the bus client path (`ops/scripts/lib/cortex_bus.py`, `bus_outbox.py`, `core/cortex_bus/server.py`, `schema/queue.sql`). Canonical implementation lives in the repo; this skill carries the design rules so future changes don't regress them.

## Invariants (never regress)

1. **4xx = permanent, fail fast.** `_bus_post` raises `BusPermanentError` on any 4xx; `bus_send` returns `{"queued": false, "permanent": true}` and never writes the client outbox. Only 5xx/timeout/conn-refused are transient. Rejected messages can never succeed — retrying burns hours of retry budget (observed: one poison message retried 12× over 17h).
2. **Auth downshift is the single 401/403 exception.** nginx ignores Bearer → retry with Basic (`CORTEX_BUS_AUTH`). Inside that inner fallback, a NEW 4xx means auth passed and the server rejected the message — re-raise as `BusPermanentError`. Do NOT swallow it as 'fallback also failed' — that reintroduces poison retries even with the outer guard.
3. **Outbox sweep quarantines permanent outcomes on first attempt**, never consuming retry budget (dir `~/.hermes-cortex/bus-retry/quarantine/`). Test the sweep against a fresh file by aging mtime first — attempt-0 files still get ~1 min backoff.
4. **Sweep resolves `bus_send` via module attribute** (`_resolved_bus_send`), not a function-local `from … import` — local imports bypass test monkeypatching.
5. **Server-side orchestrator mirror:** sends addressed to `inbox_moses`/`inbox_esther` are mirrored to `inbox_orchestrator` (original preserved in `forwarded_from`, loop-safe via early return on the mirror queue, best-effort — mirror failure never fails the primary send). All current and future orchestrators share visibility; the mirror must accept both string and dict envelopes (parse before `.get`).
6. **Handler error/crash replies go to `inbox_orchestrator`**, not personal queues — replies into `inbox_moses` had no consumer (dead letters).
7. **`recover_timeouts()` promotes pending messages at `retry_count >= max_retries` (aged 1h+) into their DLQ** (schema Step 2c) — closes stuck-pending permanently; individual `bus.archive()` cleanup is the fallback.
8. **Deploy is file-copy, not auto-apply:** schema changes go to every host's DB via `docker exec -i mycortex-postgres psql … -f /tmp/queue.sql` (scp to host home first, `docker cp` into the container — the container does not see host paths).

## TDD workflow for this path

- RED: write pytest against the deployed lib by importing via `importlib.spec_from_file_location` (lib lives outside cwd; relative import fallbacks exist).
- GREEN: edit the DEPLOYED copy (`~/.hermes-cortex/scripts/lib/`), then sync to repo (`ops/scripts/lib/`) — repo lib must be headerless (strip `SOURCE:`/banner lines that cortex-update injects into deployed copies; committing the header pollutes the repo source and fails the push gate).
- Dogfood the exact incident input end-to-end (poison send → expect `permanent: true`, zero new outbox files; mirror send → expect row in `inbox_orchestrator`).
- Orchestrator mirror needs `systemctl --user restart cortex-bus.service` after server.py changes — a running service holds old code.
- Retry-budget gotcha when testing the sweep: a fresh outbox file starts at attempt 0 and gets ~1 min backoff before the send is retried — age the file's mtime (`os.utime(f, (now-3600, now-3600))`) before invoking the sweep in tests, and expect 2-3 sweep passes to drain a batch (one per backoff age).
- Repo↔deploy sync check before push: `md5sum` both lib copies must match; the doctor's "deployed copy differs from repo source" FAIL usually means a late edit landed on only one side — re-`cp` deployed → repo (headerless) and `git commit --amend` before pushing.

## Role matrix (who is affected by what)

- Workers (gisu/joseph/kustos/titus) poll only `inbox_<agent>`; mirror/extra-queue logic is orch-only. All worker inboxes + `inbox_orchestrator` exist on the central bus.
- Non-orchestrators: HTTP client only (never install bus server or `cortex-bus` MCP). Their installs get client libs via plain `register()` in cortex-update.sh — not `register_orch`.
- Worker hosts pick up new libs at their next pull + cortex-update; don't count that lag as breakage.
