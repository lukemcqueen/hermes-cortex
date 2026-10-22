# [cost/3] Per-cron cost metrics at the sink + weekly cost-report cron — plan

Slice: `511ad057-7070-413c-9006-e87eeb639d38` (priority 3, fleet, story `c579ef95`).
Cycle: `cost3-per-cron-cost-metrics` (#13655), 2026-10-22. Author: esther (orchestrator).
Predecessor [cost/1] `5e875477` is `completed` (proof: `docs/evidence/morning-task-pass-2026-10-22/dep-cost1-status.txt`).

## 1. What the slice asks for

> add per-cron token/spend tag to metrics sink :14005 and a weekly cost-report cron with
> alert when fleet daily avg exceeds $10; verify alert fires once in test.

## 2. Measured survey (what exists today)

| Fact | Evidence |
|---|---|
| The sink at `:14005` is a reverse proxy in front of VictoriaMetrics; the client pushes Prometheus text to `/api/v1/import/prometheus` | `docs/runbooks/push-metrics-nginx-deploy.md:1-28`, `ops/install/deploy/nginx/metrics-sink.conf` |
| This host's push targets are `VICTORIA_METRICS_URL` (remote `:13005`, primary) and `VICTORIA_METRICS_FALLBACK_URL` (local `:14005`) | `~/hermes-cortex/.env:66-67` (values not reproduced — the URL carries a Basic-auth credential) |
| The push client is `ops/scripts/manage/agent-push-metrics.sh`, 403 lines, `collect_metrics()` at line 122 builds the payload, `set -euo pipefail` at line 25, pushes every 5m on every host (`agent-push-metrics`, scope universal) | `wc -l` = 403; `ops/install/cron-manifest.yaml` `agent-push-metrics` |
| The client pushes ONLY system metrics today (cpu/load/mem/disk/uptime) — no cost or token series | `grep -n -e cron -e token -e cost ops/scripts/manage/agent-push-metrics.sh` → matches are comments only |
| Per-cron token truth: `~/.hermes/cron/usage_audit.jsonl`, one JSON object per fire: `{"ts","job_id","fire_id","prompt_tokens","completion_tokens","total_tokens","model","duration_ms","error",...}` — 1740 rows on this host, first row 2026-08-09 | `read_file` line 1 of that file |
| Per-cron SPEND truth: `~/.hermes/state.db` → `sessions`, columns include `estimated_cost_usd`, `input_tokens`, `output_tokens`, `source`; cron rows are named `cron_<jobid>_<ts>` | `skills/devops/llm-cost-optimization/references/fleet-cost-data-sources.md` |
| A previous cost stack (`cron-costs.db`, `cost_store.py`, `cost-guard` plugin, `orch-daily-cost-report.py`) was REMOVED 2026-10-06 — a stored price table rotted on every provider hike | `docs/evidence/cost-removal-2026-10-06.md`; `git log --diff-filter=D -- '*cost*'` shows `e5227fa7` |
| Baseline (2 of 6 hosts measured): $9.35/13d = $0.72/day vs the story's $10/day target; the four worker hosts are unmeasured | `docs/evidence/cost-baseline-2026-10-19.txt:144-149` |
| [cost/2] and [cost/3] are orchestrator-only; the morning pass recorded `plan IS NULL` on both and held them for exactly that reason | `docs/evidence/morning-task-pass-2026-10-22/README.md:71-79,89-97` |
| Cron source of truth is `ops/install/cron-manifest.yaml` + the installer's `create_cron` block; an entry in one and not the other is flagged ORPHAN by `cron_manifest.py --check` | `skills/devops/cron-job-management/SKILL.md:45`; `docs/runbooks/orch-bus-worker-rename.md:21-23` |

## 3. Design

### 3.1 Price source — do not reintroduce a stored price table

Cost is read from Hermes' own `state.db.sessions.estimated_cost_usd` (written live per session, so it
tracks provider prices) and tokens from `usage_audit.jsonl` (append-only, no DB lock). No price constant
is added to the repo. Where a number cannot be read, the series/report says so — never a zero.

### 3.2 Per-cron series at the sink (`:14005`)

New hermetic generator `ops/scripts/manage/cron-cost-metrics.py`:

```
python3 cron-cost-metrics.py --prometheus --agent <AGENT_NAME> [--audit PATH] [--state-db PATH]
```

emits Prometheus text exposition lines on stdout:

```
hermes_cron_tokens_total{agent="<a>",job_id="<id>"} <n>          # sum of total_tokens per job_id
hermes_cron_fires_total{agent="<a>",job_id="<id>"} <n>
hermes_cron_cost_usd{agent="<a>",job_id="<id>"} <usd>            # state.db sessions, source='cron'
hermes_cron_cost_usd_total{agent="<a>"} <usd>
hermes_cron_cost_available{agent="<a>"} 1|0                      # 0 = spend unreadable: series omitted
```

The spend read is `SELECT id, estimated_cost_usd FROM sessions WHERE source='cron'` against
`~/.hermes/state.db` opened read-only (`file:…?mode=ro`) — the key column is `id`, and cron
session ids are `cron_<jobid>_<ts>`. (The first version of the generator assumed a
`session_id` column that does not exist; the verification transcript caught it — the query
matched zero rows and the series reported spend unavailable while the data was there.)

`agent-push-metrics.sh` gains one call site inside `collect_metrics()`: if
`~/.hermes-cortex/scripts/cron-cost-metrics.py` exists, append its stdout to the payload; if it exits
non-zero or is absent, the push proceeds unchanged and records one stderr line (fail-soft — a missing
generator must never turn a metrics push into a failure, and must never silently report $0).

### 3.3 Weekly cost-report cron (orchestrator-only)

New `ops/scripts/manage/orch-weekly-cost-report.py`, `no_agent: true`, schedule `0 9 * * 1`,
`deliver: telegram:{{HOME_CHANNEL}}`, scope `orchestrator`.

- Reads this host's `usage_audit.jsonl` + `state.db` sessions over a 7-day window.
- Prints total, per-day, top jobs by tokens, and a COVERAGE block naming which hosts are measured
  and which are not (a report that hides missing data is worse than none — the design rule kept from
  the removed digest, `fleet-cost-data-sources.md`).
- Alert: when the measured fleet daily average > `CORTEX_COST_DAILY_TARGET_USD` (default `10`), print
  `⚠️ FLEET COST ABOVE TARGET …` and exit 1 (cron failure → visible); otherwise exit 0 and stay quiet.
- Registered in BOTH `ops/install/cron-manifest.yaml` and the orchestrator installer's `create_cron`
  block in the same commit (orphan rule), plus a `docs/cron-schedules.md` row.

### 3.4 Tests (hermetic, no live store)

`tests/test_runtime/test_cron_cost_reporting.py` +
`tests/test_runtime/test_push_metrics_cost_series.py`:
fixture `usage_audit.jsonl` and a fixture sqlite `sessions` table (column names mirroring the
live schema) written to a temp dir, driven through the scripts' CLI with `--audit`/`--state-db`
pointed at the fixture, plus the REAL push client driven with a stub curl that records the
payload it receives:

1. above-threshold fixture → alert line present AND exit code 1;
2. below-threshold fixture → no alert line, exit 0;
3. empty/garbage audit → coverage says NO DATA, and no fabricated number;
4. sessions outside the window are excluded (the filter is what makes the number);
5. metrics generator → payload contains `hermes_cron_tokens_total{…job_id="…"}` for the fixture job;
6. the push client with the generator absent, working, and failing (fail-soft, and the failure is
   announced on stderr rather than silently reported as $0 spend).

Verified: 15 passed (`docs/evidence/cost3-per-cron-cost-metrics/verify.txt`).

## 4. Verification that will be shown (not planned prose)

- RED then GREEN of each test file (`python3 -m pytest <file> -v`), captured with exit codes.
- A stub sink: `python3 -m http.server` on a scratch port recording the request body, then the REAL
  client run with `VICTORIA_METRICS_URL` pointed at it, and `grep hermes_cron_` on the captured body —
  proving the series arrives end-to-end through the shipped client, not just from the generator.
- The weekly script run against a breaching fixture, printing its alert line and `rc=1`.
- One transcript under `docs/evidence/`, each command beside its own exit code, unmodified output.

## 5. Constraints honoured

- No stored price table (§3.1) — the removed stack's failure mode.
- `agent-push-metrics.sh` is universal: cost metrics must be cheap and fail-soft, and the change must
  not alter the existing failure accounting or exit codes.
- No new env var is invented: the one knob (`CORTEX_COST_DAILY_TARGET_USD`) is read with a default and
  documented in `docs/env-vars.md`; `VICTORIA_METRICS_URL` / `AGENT_NAME` already exist.
- The four worker hosts stay unmeasured until [cost/4] returns; the report must say so, never extrapolate.
