# Fleet Cost Baseline — 2026-10-06..2026-10-19

**Story:** c579ef95 *Fleet cost under $10/day avg + halve review queue*
**Slice:** 5e875477 `[cost/1]` — baseline fleet cost (per-agent, per-cron table; top 3 drivers)
**Measured:** 2026-10-19 KST by the orch-bus-worker cron (esther, orchestrator)
**Status:** MEASURED for 2 of 6 hosts — the ledger hole in §4 is a finding, not a footnote.

> The slice text names `docs/cost-baseline-2026-09.md`. That filename is stale — no baseline was ever
> measured in September, and the window this work can measure is October. This file is named for the
> window it contains (SOUL P13: fix the stale reference, do not reproduce it).

## 1. Sources (all live, all re-runnable)

- **S1 Langfuse** (local `localhost:3000`) — per-trace cost, tagged `platform:cron` +
  `trigger:cron` + `cron-job:<id>`. Daily rollup:
  `GET /api/public/metrics/daily?limit=20`; traces:
  `GET /api/public/traces?fromTimestamp=<iso>&toTimestamp=<iso>&limit=100&page=N&fields=core,usage,metrics`
- **S2 `~/.hermes/cron/usage_audit.jsonl`** — one JSON object per cron fire with
  `prompt_tokens` / `completion_tokens` / `total_tokens` / `model` / `job_id`. This is the
  completeness check: it records every fire even when S1 records nothing.
- **S3 OpenRouter `/api/v1/credits`** — account-level all-time spend (needs an inference key).

`/api/v1/activity` (per-day, per-model account spend) returns **403** with the key this host holds:
that endpoint requires a *provisioning/management* key. Account-level per-day spend is therefore NOT
retrievable today. **Account gross (S3, 2026-10-19):** `total_usage` $1,926.76 of `total_credits`
$2,008, all-time, all hosts, no split.

## 2. Headline

- **Cron compute is far under the story target.** esther cron cost is **$3.98 over the 7
  Langfuse-recorded days** (10-13..10-19), plus **~$3.54 estimated for the 6 unrecorded days** (§4)
  → **~$7.53 / 13 days ≈ $0.58/day** on esther.
- **moses (host 2)** burned **207.1M cron tokens over 157 fires** in the same window →
  **~$1.82** at esther's blended cron rate.
- **Two-host cron total ≈ $9.35 / 13 days ≈ $0.72/day** — roughly **14× under** the $10/day fleet
  target, before the 4 unmeasured hosts are added.
- **Cron is not where the money goes.** On esther, cron traces total **$3.98** while **interactive**
  traces (Telegram sessions + subagents) total **$17.24** — **4.3× the cron spend**. A cost program
  that only tunes crons targets ~19% of classified spend.

## 3. esther — per-day (S1 cost + S2 tokens)

| date | cron fires | cron tokens (M) | cron cost $ (S1) | interactive $ | unclassified $ | day total $ |
|---|---|---|---|---|---|---|
| 2026-10-06 | 21 | 62.6 | **not recorded** | 0.0000 | 3.1479 | 3.1479 |
| 2026-10-07 | 20 | 49.3 | **not recorded** | 0.0000 | 0.0000 | 0.0000 |
| 2026-10-08 | 21 | 85.8 | **not recorded** | 0.0000 | 0.0000 | 0.0000 |
| 2026-10-09 | 29 | 77.6 | **not recorded** | 0.0000 | 0.0000 | 0.0000 |
| 2026-10-10 | 23 | 36.0 | **not recorded** | 0.0000 | 0.0000 | 0.0000 |
| 2026-10-11 | 23 | 97.4 | **not recorded** | 0.0000 | 0.0000 | 0.0000 |
| 2026-10-12 | 45 | 56.2 | **not recorded** | 0.0000 | 0.0000 | 0.0000 |
| 2026-10-13 | 22 | 56.2 | 0.4599 | 0.8472 | 0.0000 | 1.3072 |
| 2026-10-14 | 24 | 60.3 | 0.6601 | 11.1333 | 0.0000 | 11.7934 |
| 2026-10-15 | 25 | 106.2 | 1.1565 | 0.7322 | 0.0000 | 1.8887 |
| 2026-10-16 | 22 | 56.0 | 0.8429 | 1.1099 | 0.0000 | 1.9528 |
| 2026-10-17 | 11 | 68.2 | 0.6062 | 1.1522 | 0.0000 | 1.7584 |
| 2026-10-18 | 16 | 37.2 | 0.1570 | 1.8695 | 0.0000 | 2.0266 |
| 2026-10-19 | 10 | 30.9 | 0.1019 | 0.3910 | 0.0000 | 0.4929 |

Traces before 2026-10-13 carry only the generic `hermes`/`langfuse` tags — the `trigger:`/`cron-job:`
tags were added mid-window — so 10-05 and 10-06 land in "unclassified".

## 4. The ledger hole (the most important finding)

| date | cron fires (S2) | cron tokens (M) | cron cost (S1) |
|---|---|---|---|
| 2026-10-07 | 20 | 49.3 | **not recorded** |
| 2026-10-08 | 21 | 85.8 | **not recorded** |
| 2026-10-09 | 29 | 77.6 | **not recorded** |
| 2026-10-10 | 23 | 36.0 | **not recorded** |
| 2026-10-11 | 23 | 97.4 | **not recorded** |
| 2026-10-12 | 45 | 56.2 | **not recorded** |

**Langfuse ingested nothing for 6 consecutive days (10-07..10-12) while 161 cron fires and 402.4M cron
tokens were burned** — S2 proves the fires happened. Extrapolating esther's blended cron rate
($0.01/Mtok, derived from the 7 recorded days) the missing cost is **~$3.54**: the Langfuse ledger
undercounts this window by roughly half. Any cost report built on Langfuse alone silently
under-reports whenever this happens; the audit log is the completeness check, and a gap like this
should raise a watchdog alert rather than be discovered by hand.

## 5. esther — per-cron (window 10-06..10-19)

| cron | fires | tokens (M) | Langfuse cron $ (tagged) |
|---|---|---|---|
| local-daily-soul-refinement | 13 | 139.6 | 0.5059 |
| local-daily-sustainability-briefing | 13 | 130.3 | 0.2449 |
| orch-bus-worker | 21 | 121.9 | 1.3336 |
| orch-skill-lifecycle | 6 | 66.7 | 0.2928 |
| cortex-bus-workday | 28 | 57.5 | 0.3041 |
| cortex-bus-overnight | 9 | 53.8 | 0.2224 |
| cortex-bus-evening | 19 | 46.5 | 0.2091 |
| orch-task-morning-pass | 13 | 40.0 | 0.1171 |
| local-weekly-loop-eval | 2 | 32.0 | 0.0350 |
| orch-skill-evaluate | 3 | 29.8 | — |
| agent-fixer-evening | 19 | 29.0 | 0.1201 |
| agent-fixer-workday | 28 | 24.9 | 0.1983 |
| agent-mycortex-dream-nightly | 13 | 23.3 | 0.0595 |
| agent-agents-md-prune-apply | 11 | 20.4 | 0.0712 |
| (job id c975d8f8aa25 — not in jobs.json) | 61 | 18.4 | — |
| agent-fixer-overnight | 9 | 15.0 | 0.0889 |
| agent-memory-pruning | 2 | 13.6 | 0.0108 |
| orch-task-evening-pass | 14 | 6.0 | 0.0564 |
| local-agent-daily-ai-brief | 13 | 5.0 | 0.0680 |
| agent-mycortex-dream-weekly | 2 | 4.3 | 0.0092 |
| local-job-opportunity-scanner | 13 | 1.9 | 0.0370 |

A blank cost cell means no `cron-job:`-tagged trace exists for that cron: it fired only inside the
§4 hole, or its traces were untagged. Tokens are S2 and cover all 14 days.

## 6. moses (host 2) — tokens only

moses' own Langfuse holds **1 trace** for the window (cost $0.0002) — it is effectively not
ingesting, so no per-day cost is available. Its audit log is complete and comparable:

| date | 2026-10-06 | 2026-10-07 | 2026-10-08 | 2026-10-09 | 2026-10-10 | 2026-10-11 | 2026-10-12 | 2026-10-13 | 2026-10-14 | 2026-10-15 | 2026-10-16 | 2026-10-17 | 2026-10-18 | 2026-10-19 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tokens (M) | 13.8 | 8.0 | 15.0 | 9.9 | 1.5 | 5.3 | 7.9 | 14.8 | 25.8 | 25.2 | 17.3 | 17.7 | 41.0 | 4.0 |

Window total **207.1M tokens / 157 fires** → **~$1.82** at esther's blended cron rate.
Top moses crons by tokens: orch-bus-worker (61.8M/22 fires), orch-skill-lifecycle (29.0M/6 fires), agent-fixer-evening (27.4M/20 fires).

## 7. Top 3 cost drivers (esther, measured)

1. **Interactive Telegram sessions — $17.24** of $21.22 classified spend. Human-driven, not schedulable.
2. **Interactive subagent sessions** — inside that same bucket; 18 `platform:subagent` traces cost
   $6.74 on their own, and 2026-10-14 alone carried $11.13 of interactive spend.
3. **`orch-bus-worker` — $1.33** (22 tagged traces), the most expensive cron; then
   `local-daily-soul-refinement` $0.51 and `cortex-bus-workday` $0.30.

Token ranking differs: `local-daily-soul-refinement` (139.6M), `local-daily-sustainability-briefing`
(130.3M) and `orch-bus-worker` (121.9M) are the top three **token** consumers, but they are cheap per
token — almost all of that input is cache-hit.

## 8. Coverage — what is NOT measured

- **2 of 6 hosts.** esther (S1+S2) and moses (S2 only). kustos, titus, joseph, gisu: **not measured**.
- **moses Langfuse is effectively dead** (1 trace) — its cost is an extrapolation, not a measurement.
- **OpenRouter per-day/per-model account spend is unavailable** (403; inference key, not a
  provisioning key). $1,926.76 all-time is the only account-level number.
- Interactive/subagent spend is esther-only and is not part of the story's "fleet cost" target as
  written, yet it dwarfs cron spend here.

## 9. Verdict against the story

- **Cron compute target ($10/day avg): PASS on the measured hosts** — ~$0.58/day esther, ~$0.14/day moses.
- The story's real risks are elsewhere: (a) the 6-day telemetry hole means cost cannot currently be
  reported continuously; (b) interactive sessions outspend crons 4.3× on esther, so cron tuning alone
  targets the minority of spend.
- **Next slices:** (1) fix the Langfuse ingest gap and alert on it (the hole, not the number);
  (2) collect kustos/titus/joseph/gisu audit logs to make the baseline fleet-wide; (3) obtain a
  provisioning key so `/api/v1/activity` can cross-check the account total independently.

## 10. Evidence

Raw commands and outputs: `docs/evidence/cost-baseline-2026-10-19.txt`.

All cost figures are live reads taken 2026-10-19 ~22:2x KST. Re-running the same commands
later will show sub-cent drift on the current day (2026-10-19 grew $0.4929 -> $0.4981 between
two reads minutes apart, and the Langfuse daily endpoint and trace aggregation may differ by a
few thousandths for the same day) — that is live data, not an inconsistency.

