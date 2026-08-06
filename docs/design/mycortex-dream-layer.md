# Mycortex Dream Layer — Design

> Status: implemented 2026-08-06 · Optional feature, removable per-agent.
> Replaces the decommissioned gbrain creative-dream cron with a richer,
> write-back-to-brain serendipity layer built on the mycortex CLI.

## Why

The gbrain design doc deliberately cut the dream/synthesis layer ("nobody
consumed it"). Luke wants it back — and expanded beyond the old weekly
~200-word summary. The mycortex brain (markdown-in-git + Postgres + cron)
gives us real raw material the old gbrain never indexed: 631+ saved
lessons, full session history, the fleet repo itself, and per-agent
bible notes.

## Architecture

**Three tiers, all LLM-driven crons** (deepseek-v4-flash), each writing
its output back into the agent's brain so dreams accumulate and connect
across runs:

| Tier | Cron | Schedule | Inputs | Output |
|---|---|---|---|---|
| 1 — Nightly digest | `agent-mycortex-dream-nightly` | `0 23 * * *` | `mycortex list -n 20`, session search | `~/brain/<agent>/dreams/YYYY-MM-DD.md` (~100-150 words) |
| 2 — Weekly deep dream | `agent-mycortex-dream-weekly` | `0 3 * * 6` | `mycortex list -n 30` + search, week's `~/brain/lessons/`, bible notes | `~/brain/<agent>/dreams/YYYY-MM-DD-weekly.md` (~200-250 words) |
| 3 — Monthly arc | `agent-mycortex-dream-monthly` | `0 3 1 * *` | `git log` 30d, lessons count, `mycortex stats`, knowledge-gap probe | `~/brain/<agent>/dreams/YYYY-MM-monthly.md` (~300 words) |

### Cross-run connection

Every tier appends a line to `~/brain/<agent>/dreams/INDEX.md`:
`YYYY-MM-DD | title | one-line summary`. New dreams are instructed to
read the INDEX (and 2-3 recent dreams) first, so each dream can
reference its predecessors — the brain's memory of its own dreaming.

### Dream sources (what each tier actually queries)

- **Tier 1:** `mycortex list -n 20` (fresh pages) + session_search for
  today's work + `mycortex search "<topic>" --limit 3` for connections.
- **Tier 2:** `mycortex list -n 30`; `mycortex search` to map 3-5 page
  connections; `ls ~/brain/lessons/` + read 3-5 recent lesson files to
  surface recurring patterns; `~/brain/<agent>/bible/INDEX.md` + the
  week's scripture note for the soul-level connection (graceful skip if
  no bible dir — makes Tier 2 portable to non-Esther agents).
- **Tier 3:** `git -C ~/hermes-cortex log --since="30 days"` for the
  work arc; `ls ~/brain/lessons/ | wc -l` + `mycortex stats` for
  scale; and a knowledge-gap probe — take 3-5 topics the week's work
  touched and `mycortex search` each; topics with zero/no strong hits
  become "the brain knows nothing about X yet" flags.

### Rules (every tier)

1. **Real connections only** — never fabricate page relationships.
   Every claimed link must come from an actual `mycortex search` result
   or a real file read.
2. **Write-back is mandatory** — the dream is not done until the file
   exists in `~/brain/<agent>/dreams/` AND the INDEX line is appended.
   A dream that only ships to Telegram is half a dream.
3. **[SILENT] only when the brain is genuinely empty** — otherwise
   deliver. These are serendipity crons, not watchdogs.
4. **Agent-name discovery:** `hostname` or `AGENT_NAME` env (esther,
   moses, joseph, kustos, gisu, titus) — never hardcode a path.
5. **Standard cron output format** (cron-format-standard): header,
   phases, Result, cost footer — with the file paths written as the
   Phase evidence.

## Removability (explicit requirement)

The whole layer is **optional and removable per-agent**:

- All three crons live in **`ops/scripts/install/install-dream-crons.sh`**
  (own create_cron blocks + own uninstall array). They are NOT in
  `install-crons.sh` / `install-orch-crons.sh`, so the doctor does not
  expect them fleet-wide and non-participating agents never get them.
- **Install:** `bash ~/hermes-cortex/ops/scripts/install/install-dream-crons.sh`
- **Remove:** `bash ~/hermes-cortex/ops/scripts/install/install-dream-crons.sh --uninstall`
  (removes the three crons; dream files in `~/brain/<agent>/dreams/`
  are kept — they're knowledge, not cruft).
- No dream cron is in any doctor expected-list, so removal never
  triggers a false doctor FAIL.

## Delivery

All three use `deliver: origin` (chat captured at creation — verified
non-null, avoiding the 2026-08-06 silent-cron bug: script-created crons
got origin=null and delivered nowhere; explicit capture at create time
fixes it). The weekly + monthly also write the dream file (write_file),
so `enabled_toolsets: ["terminal","file"]`; nightly uses
`["terminal","file"]` too (INDEX append).

## Cost

~$0.006/run deepseek-v4-flash: nightly ≈ $0.18/mo, weekly ≈ $0.03/wk
≈ $0.13/mo, monthly ≈ $0.01/mo. Total ≈ **$0.32/mo per agent**.

## History

- 2026-08-02: gbrain decommissioned; dream crons removed; design doc
  explicitly excluded dream/synthesis ("nobody consumed it").
- 2026-08-06: Luke asks to restore + expand; nightly + weekly created
  first, then redesigned into this 3-tier write-back layer with monthly
  tier and optional installer.
