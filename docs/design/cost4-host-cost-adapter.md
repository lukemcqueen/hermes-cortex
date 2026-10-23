# [cost/4] Fleet cost coverage — per-host audit-log adapter (plan)

Slice `6b7d9b8a` (priority 2, fleet, story `c579ef95`). Cycle **#13765**,
task id `cost4-host-cost-summary`, session `cron_1954deb5ad76_20261024_082143`.
Author: esther (orchestrator). Status: **plan — submitted for review before any
code is written** (operator standing rule).

## 1. What the slice asks for

Paraphrase of the recorded slice text (`6b7d9b8a`), not a verbatim copy — the
imperatives in the original are the slice's instructions to its worker, not
instructions in this plan.

The story's cost baseline covers 2 of 6 hosts, so its under-target verdict is an
extrapolation rather than a fleet measurement. Each worker host can read only its
own cron usage audit log, so the slice is one plan with four per-host adapters.
Per worker host, read-only, about five minutes of work: (1) aggregate that host's
cron usage audit log — one JSON object per cron fire, carrying prompt, completion
and total token counts, model and job id — into per-day fire counts, per-day token
totals, and per-job totals, for the window from 2026-10-06 to now; (2) if the host
runs a Langfuse instance, read its daily metrics endpoint once and report traces and
cost, otherwise record plainly that the host has none; (3) keep the raw command
output in a file on that host and reply to esther with the path plus the numbers;
(4) a host missing a needed tool returns the slice with the gap named rather than a
number. Measurement only — the slice explicitly excludes any config or cron change.
Acceptance: the four host aggregates can be pasted into the coverage section of the
cost baseline, taking 2 of 6 hosts measured to 6 of 6.

## 2. Measured starting state

| Fact | Evidence |
|---|---|
| Baseline covers 2 of 6 hosts: $9.35 over 13 days = **$0.72/day** vs the story's $10/day target; the four worker hosts are unmeasured | `docs/evidence/cost-baseline-2026-10-19.txt:144-149` (block 5 = remote aggregation on host 2, block 6 = derived figures) |
| Four `TASK_REQUEST`s were sent for this slice on 2026-10-22 07:39 KST and were **consumed with no closure**: all four worker inboxes drained, `inbox_esther` empty, no `TASK_RESULT`, and `tasks.task_events` for `6b7d9b8a` contains only `created` | `docs/evidence/morning-task-pass-2026-10-23/README.md` §"Dispatch: 0 (hold)" and its two artifacts |
| **Why**: the `TASK_REQUEST` handler executes nothing. `ops/scripts/agent/commands.py:659-693` (`handle_task`) logs the task text and returns `{"success": true, "forwarded_to": "luke"}`. A measurement slice dispatched as free text to a worker whose only handler records prose cannot produce numbers by construction — the 10-22 send was the wrong channel, not a worker failure | `ops/scripts/agent/commands.py:659` |
| The `EXEC` handler **does** execute: it resolves the command under `~/.hermes-cortex/scripts/` (absolute paths also accepted), runs it with `sys.executable` if `.py`, and returns `stdout`/`stderr`/`exit_code` in an `EXEC_RESULT` | `ops/scripts/agent/commands.py:328-361`, registered at `:702` |
| `cron-cost-metrics.py` is already deployed to every host and already runs on every host: it is a deploy-map entry and is invoked every 5 minutes by the universal `agent-push-metrics` cron | `~/.hermes-cortex/deploy-manifest.tsv:315`; `docs/design/cost3-per-cron-cost-metrics.md` §3.2 |
| What it does **not** have: a window filter and a per-day breakdown. It emits lifetime per-job `tokens`/`fires` and lifetime per-job spend. The slice asks for per-day fires + per-day tokens **over a window**, plus per-job totals | `ops/scripts/manage/cron-cost-metrics.py:34-60, 132-154` (no `--since`; `read_tokens` sums all rows) |
| Identity is already resolved host-side by an existing helper, not by whoami/hostname: env `AGENT_NAME` → `~/.hermes-cortex/agent.env` → `~/hermes-cortex/.env`, hard error otherwise | `ops/scripts/agent/commands.py:33-54` (`_agent_name`) |

## 3. Design

### 3.1 Patch the deployed generator; do not add a sixth script

`survey-before-action` §2 puts a tool that covers more than 80% of the need in
"patch the existing tool". This one already reads both cost truths, is already
deployed on all six hosts, and already runs on all six every 5 minutes — so the
adapter is a **mode on it**, not a new file. Adding a new script would need its own
deploy-map entry, its own registration, and a `cortex-update` on every worker before
the first measurement could be taken.

### 3.2 Change to `ops/scripts/manage/cron-cost-metrics.py`

Two additive options, default behaviour untouched:

```
python3 cron-cost-metrics.py --prometheus  --agent <a> [--audit P] [--state-db P]      # unchanged
python3 cron-cost-metrics.py --json-summary [--agent <a>] [--audit P] [--state-db P] [--since YYYY-MM-DD]
```

- `--since YYYY-MM-DD` filters audit rows (and, when given, cron sessions) to
  `date(ts) >= since`, UTC, by the row's own `ts` field. Rows with a missing or
  unparseable `ts` are **counted in `skipped_rows`, never silently included**.
- `--json-summary` prints ONE compact JSON object on stdout, sized to fit an
  `EXEC_RESULT` body:

```json
{"agent":"joseph","host":"<nodename>","generated_at":"2026-10-24T08:30:00Z",
 "audit":{"path":"~/.hermes/cron/usage_audit.jsonl","rows":550,"skipped_rows":0,
          "first_ts":"2026-08-09T14:27:52Z","last_ts":"2026-10-24T08:00:01Z"},
 "window":{"since":"2026-10-06"},
 "per_day":[{"date":"2026-10-06","fires":14,"tokens":13804567}],
 "per_job":[{"job_id":"orch-bus-worker","fires":22,"tokens":61759790}],
 "spend":{"available":true,"lifetime_usd":1.3388,"per_job":{"1954deb5ad76":1.3388}},
 "langfuse":{"checked":false,"reason":"not probed by this tool"}}
```

- `per_day` is ascending by date; `per_job` is descending by tokens and **capped**
  (top 15) with `per_job_omitted` carrying the remainder count, so a host with many
  jobs still returns a body that fits.
- Identity: `--agent` default becomes env `AGENT_NAME` → `~/.hermes-cortex/agent.env`
  → `~/hermes-cortex/.env`, mirroring `commands.py:_agent_name`. A host that cannot
  resolve its own name still exits 2 and says so — the tool never labels a host
  `unknown` (SOUL P3: tooling identity is host-derived).
- Modes are mutually exclusive and exactly one is required.
- Exit codes unchanged and documented: `0` = series/JSON emitted, `2` = nothing
  readable at all or no identity. An unreadable spend source is reported as
  `"spend": {"available": false, "reason": "..."}` — never as `0` (the rule the
  removed price-table stack died for, `docs/evidence/cost-removal-2026-10-06.md`).
- Langfuse is **not** probed by this tool. The slice's item (2) is a per-host check
  the worker reports in its reply, and inventing a second client for it inside a
  metrics generator is scope this cycle does not take.

### 3.3 Dispatch: `EXEC`, proven on esther first

```
EXEC body = {"topic":"fleet-update","command":"cron-cost-metrics.py",
             "params":["--json-summary","--since","2026-10-06"],"timeout":60}
correlation_id = cost4-<12 hex>
```

sent to `inbox_joseph`, `inbox_gisu`, `inbox_kustos`, `inbox_titus` — the four
`role != orchestrator` hosts in `~/.hermes-cortex/state/agent-registry.json`, which
is also where `orch-bus-fleet-dispatch.py:73-94` reads its agent list.

Before any worker send, the identical `EXEC` goes to **`inbox_esther`** on this host:
the round trip (send → consume → handler log → `EXEC_RESULT` read back by me) is
proven locally first, per `cross-agent-design` and the skill's "prove on yourself
first" rule. The four worker sends happen only after that local `EXEC_RESULT` carries
real numbers.

Note on the result path: `handle_exec` returns its result to the *sender-agnostic*
`send_bus_result`, which posts to `inbox_moses` (`commands.py:113-134`). So the four
`EXEC_RESULT`s are read from moses' bus, by ssh, not from this host's mirror.

Non-destructive by design: every dispatch is read-only and the message carries no
config change (`params` are inspection flags only).

### 3.4 Tests (hermetic, no live store) — written RED first

Appended to the existing `tests/test_runtime/test_cron_cost_reporting.py`, driving
the script's real CLI against temp fixtures (its `_audit` / `_sessions_db` helpers):

1. window filter: a row inside `--since` is counted; one before it is excluded —
   the filter is what makes the number;
2. `per_day` splits by the row's own UTC date and sums tokens + counts fires per day;
3. rows with no/bad `ts` land in `skipped_rows` and are not counted anywhere else;
4. `per_job` is descending by tokens and the cap is declared (`per_job_omitted`);
5. absent `--agent` and no env identity → rc 2 with the `AGENT_NAME` message, and
   `--json-summary` on a host whose `agent.env` carries `AGENT_NAME=` resolves it;
6. unreadable `--state-db` → `spend.available == false`, no `lifetime_usd` key, and
   still rc 0 (an unavailable source is not "no data at all");
7. `--prometheus` output is byte-identical to the pre-change revision for the same
   fixture (default behaviour untouched);
8. exactly one mode may be given: neither, or both, is a usage error.

Test 7 is the regression guard for the universal producer: `agent-push-metrics.sh`
(288 runs/day/host) must keep receiving the same payload.

### 3.5 Verification that will be shown

- RED then GREEN of the normed test file with exit codes, captured unmodified under
  `docs/evidence/cost4-host-cost-adapter/`.
- The deployed copy run for real (`~/.hermes-cortex/scripts/cron-cost-metrics.py`)
  beside the repo copy, to show the deployed path emits the same JSON.
- The local `EXEC` self-test round trip: the sent envelope, the consumed message, the
  handler log line, and the `EXEC_RESULT` read back with real numbers.
- Each command printed beside its own exit code; numbers quoted only from the
  committed transcript.

## 4. Rejected options

| Option | Why not |
|---|---|
| New `host-cost-aggregate.py` script | The generator already covers the need and is already on all six hosts; a new file costs a deploy-map entry, a cortex-update on every worker, and a second code path that rots. `survey-before-action` §2. |
| Dispatch the slice as `TASK_REQUEST` again | Measured: `handle_task` executes nothing (`commands.py:659`). That is what produced the 10-22 "consumed with no closure". |
| Read the other five hosts' audit logs from this host | The slice's own premise: each host can only read its own log, and hardcoding another host's layout is what it forbids. Also fails on portability. |
| Write the handed-out state/plan into the task row to make the dispatch visible | The orchestrator write surface does not exist (`task-db.py update` exposes only `--status/--reason`), and raw SQL bypasses the single write path — explicitly forbidden by the fix direction recorded in task `9fb2ddb6`. Tracked there, not here. |
| Extend `per_job` to per-host cost by re-deriving spend from a price table | The stored-price stack was removed 2026-10-06 because prices rot; Hermes' own `sessions.estimated_cost_usd` is the spend truth. |

## 5. Out of scope (reported, not silently dropped)

- The four per-host Langfuse checks (slice item 2) ride in the workers' replies; this
  cycle ships the transport and the audit-log half.
- `orch-weekly-cost-report.py`'s COVERAGE block is the consumer of these numbers; it
  is updated in the cycle that pastes the four aggregates in, not here.
