# Backlog run — `orch-bus-worker` gives itself a verification surface (2026-10-25)

Governance cycle **#13788**, session `cron_1954deb5ad76_20261025_222143`, task id
`bus-mcp-verify-surface`. Backlog row closed: `5c200dd0-1797-4153-b452-5977a727ba48`
("orch-bus-worker on esther cannot VERIFY a bus dispatch — its dispatch half is
structurally fire-and-forget"), priority 2, personal scope.

## 0. Backlog at the time of the run

```
pending (claimable): 15   pending (not claimable): 7   pending (story): 3
in_progress: 1            in review: none              blocked: 3   paused: 10
```

Top row by (priority desc, created_at) is `c579ef95`, priority 3, **kind=story**
(not claimable). The first pending row that is a real task, orchestrator-local,
and finishable **and verifiable** unattended is `5c200dd0` — this job's own
structural block, so fixing it is also what makes every later run honest.

## 1. The claim, and what was measured

The row says the driver cannot verify a dispatch: (1) fleet results land in
`inbox_moses` archives while the only read surface is `mcp__agent_bus__inbox_read`,
hard-filtered to `inbox_esther`; (2) `inbox_send` has no `correlation_id`, so a
result is unmatchable even when visible.

Both were confirmed at code level before being accepted:

- `AGENTS.md` line 86 — the bus ingestion allowlist **already includes
  `correlation_id`**: ``(`from` `to` `subject` `body` `correlation_id` `timestamp` `priority` `type`)``.
- `mcp-servers/cortex-bus-mcp.py` `_inbox_send` built its envelope inline with no
  `correlation_id` key, and the `inbox_send` / `inbox_send_task` input schemas had
  no such property — so a caller could not supply one at all.
- `_inbox_read` dequeues with `POST /api/pgmq/read` on `queue: inbox_{DEFAULT_AGENT}`
  — a **consuming** read of the caller's own queue.
- A non-destructive surface already existed and was unused by the MCP:
  `core/cortex_bus/server.py` line 438 `GET /api/pgmq/peek/{queue}` ("Peek pending
  messages without consuming") and line 477 `GET /api/pgmq/archives/{queue}`
  (added precisely because "the live peek endpoint only sees 'pending' messages —
  results that the handler already archived are invisible to it").

### 1a. A correction: my first probe was wrong, and it was mine

My first probe (`~/.hermes/cache/scratch/probe-verify-surface.py`) reported the
primary bus as **HTTP 401 for every queue**, and I drafted an evidence note
claiming fleet results were simply "unauthorized". That was a **probe defect**: it
returned Bearer *or* Basic — never both — so with a bearer token configured it
never made the Basic attempt that the MCP's own cascade makes.

Reading the MCP's real endpoint chain and response, the primary bus answers
**Basic** (the Bearer attempt 401s and cascades, then Basic succeeds). The
`HTTP 401` line in that first transcript describes the first endpoint attempt, not
the readable result. The corrected statement is the one below, taken from the
live run through the shipped code path. This correction is recorded rather than
quietly dropped: the wrong version was in the plan handed to the reviewer.

## 2. The change

One file changed (`mcp-servers/cortex-bus-mcp.py`) plus one new test file
(`tests/test_bus_mcp_verify_surface.py`). Additive only; no gate touched.

1. `_inbox_send` now builds the envelope through a local `_envelope(to_name)`
   helper that adds `"correlation_id"` **only when the caller supplies a
   non-blank value** — so every existing caller posts a byte-identical envelope.
   Used by both the single-recipient and the broadcast path.
2. `inbox_send` and `inbox_send_task` schemas gained an optional
   `correlation_id`; `_inbox_send_task` passes it through to `_inbox_send`.
3. New tool `bus_inbox_peek` (`_bus_inbox_peek`): `GET /api/pgmq/peek/{queue}` or
   `GET /api/pgmq/archives/{queue}`, default queue `inbox_orchestrator`, returning
   each message's `subject` / `correlation_id` / `from` / `enqueued_at`. It never
   issues `POST /api/pgmq/read`: a verification read must not consume the result
   it is trying to observe. An HTTP failure returns an explicit
   `peek failed … (HTTP nnn)` string rather than an empty list, so a 401 can never
   read as "nothing arrived".

## 3. Evidence

### 3.1 Unit tests green, on the changed functions

```
$ /home/esther/.hermes-cortex/venv/bin/pytest tests/test_bus_mcp_verify_surface.py -q
collected 9 items
tests/test_bus_mcp_verify_surface.py .........                           [100%]
============================== 9 passed in 1.27s ===============================
```

### 3.2 Non-vacuity — the same tests against the PRE-change module

```
$ git show HEAD:mcp-servers/cortex-bus-mcp.py > <scratch>/mcp-servers/cortex-bus-mcp.py
pre-change module correlation_id occurrences: 0
pre-change module has bus_inbox_peek: 0
$ <venv>/pytest tests/test_bus_mcp_verify_surface.py -q      # in that scratch tree
FAILED test_inbox_send_carries_correlation_id_in_envelope
FAILED test_inbox_send_task_passes_correlation_id_through
FAILED test_bus_inbox_peek_never_consumes
FAILED test_bus_inbox_peek_archived_uses_archives_endpoint
FAILED test_bus_inbox_peek_exposes_correlation_id_from_nested_body
FAILED test_bus_inbox_peek_reports_http_failure_not_an_empty_queue
FAILED test_bus_inbox_peek_defaults_to_orchestrator_queue
7 failed, 2 passed in 1.14s
```

The 2 passers are the "absent / blank correlation_id stays absent" cases, which
are true of the old revision by construction — they assert the legacy shape is
preserved, so they *should* pass on both.

### 3.3 Live end-to-end through the shipped code path (real bus, not a mock)

`bus_inbox_peek` on the orchestrator queue returned real traffic:

```
== 2. bus_inbox_peek(inbox_orchestrator) ==
{ "queue": "inbox_orchestrator", "archived": false, "count": 2, "messages": [
    { "msg_id": "ef76e6a6-…", "enqueued_at": "2026-10-25 13:25:24.518115+00",
      "read_ct": null, "from": "esther", "to": "esther",
      "subject": "DOCTOR_TEST", "correlation_id": "doctor-e2e-310be956" },
    { "msg_id": "a1e732bc-…", "enqueued_at": "2026-10-25 13:25:38.37922+00",
      "read_ct": null, "from": "esther", "to": "moses",
      "subject": "HEALTH_PERSISTENT_ISSUES" } ] }
```

The full loop — send **with** a correlation id, then read it back — closed on the
live bus:

```
== 3. send DOCTOR_TEST to own inbox with correlation_id=verify-surface-702a3eb477 ==
Message sent.
== 4. peek own inbox back ==
count=1
match on correlation_id: True
   {"msg_id": "f75c60d5-c7a7-4009-8565-42b3cd799927", …,
    "subject": "DOCTOR_TEST", "correlation_id": "verify-surface-702a3eb477"}
```

The bus **accepted** the envelope carrying `correlation_id` (no 400), which the
unit test alone could not show. The self-test message was then archived
(`mcp__agent_bus__inbox_delete` → "Archived: f75c60d5-…") and the queue
re-measured as `inbox_esther count= 0`.

And the row's exact failure mode — a result that has already been **archived** —
is now readable:

```
$ bus_inbox_peek(queue='inbox_moses', archived=True)
inbox_moses ARCHIVED count= 7
    DOCTOR_TEST | corr= doctor-e2e-07d18e94 | moses | 2026-10-25 13:15:13.202945+00
    DOCTOR_TEST | corr= doctor-e2e-ac9994a1 | moses | 2026-10-25 13:10:33.135198+00
    …
```

## 4. Residual / limits, stated rather than glossed

- The running session's MCP tool list is built at session start, so
  `bus_inbox_peek` becomes callable by the `orch-bus-worker` cron from its next
  run — the live evidence above exercises the same handler code directly.
- Peek is a **window, not a census**: it returns at most `limit` messages. A
  result older than the window needs a larger `limit` or an archive read; the
  exact depth remains available from `GET /api/pgmq/queues` (as
  `bus-inbox-inspect.py` already relies on).
- This change makes dispatch results *readable and matchable*. It does not make a
  fleet host *respond*. Closing a dispatched fleet slice still requires the
  target's real `EXEC_RESULT`; nothing here is evidence that any host replied.

## 5. Re-run

```bash
/home/esther/.hermes-cortex/venv/bin/pytest tests/test_bus_mcp_verify_surface.py -q   # expect 9 passed
python3 ~/.hermes/cache/scratch/live-verify-surface.py                                  # live bus loop
```
