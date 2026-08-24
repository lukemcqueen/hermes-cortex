---
name: agent-ergonomic-cli-output
description: "Agent-facing CLI output: token-lean by design (AXI/TOON)."
version: 1.0.0
author: Hermes Cortex (Esther)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cli, output, tokens, toon, axi, agent-facing, ergonomics]
    related_skills: [cron-format-standard, change-checklist]
---

# Agent-Ergonomic CLI Output

AXI (Agent eXperience Interface) principles distilled for fleet scripts:
make agent-facing CLI output token-lean and decision-ready. The expensive
token cost is not a longer response — it is the FOLLOW-UP CALL. Every
principle below eliminates one. Deep reference (full mapping to Cortex
surfaces, ranked quick wins): `~/hermes-cortex/docs/axi-agent-ergonomics.md`.

## When to Use

- Building or modifying any script whose stdout an agent reads (hc, doctor,
  watchdogs, bus previews, task-db, health scripts)
- Reviewing an existing script's output for token waste or ambiguous output
- Don't use for: human chat replies (AXI governs agent-consumed surfaces,
  not conversation) or machine protocols (bus wire format and MCP transport
  stay JSON — TOON is an output-boundary format, never a transport).

## The 10 Principles (condensed)

1. **Token-efficient output** — TOON-lite over JSON on stdout: `name[N]{fields}:` header + CSV rows, ~40% token savings. Convert at the output boundary; keep JSON internally.
2. **Minimal default schemas** — id/title/status, 3-4 fields not 10+; offer `--fields` to request more; default limits cover common cases in one call.
3. **Content truncation** — truncated preview + `... (truncated, N chars total)` + `--full` escape hatch. Never omit large fields entirely.
4. **Pre-computed aggregates** — totals (`count: 30 of 847 total`) and derived statuses (`checks: 3/3 passed`); include what agents would otherwise round-trip for.
5. **Definitive empty states** — `queue: 0 messages` with context; never bare empty output (agents re-run to verify ambiguity).
6. **Structured errors & exit codes** — errors on stdout in the same format as data with an actionable suggestion; exit 0 success (incl. idempotent no-ops) / 1 error / 2 usage; fail loud on unknown flags (never silently drop flags); no interactive prompts.
7. **Ambient context** — session-start dashboards: ≤15 lines, ruthlessly minimal (loads every session); session-end capture enriches the next start.
8. **Content first** — no-args shows live data, not a usage manual.
9. **Contextual disclosure** — 1-3 complete next-step commands after lists/mutations (placeholders like `<id>` for runtime values); omit when output is self-contained; on errors suggest the fixing command, not `--help`.
10. **Consistent help** — per-subcommand `--help` (flags + defaults, 2-3 examples); fast bare `--version` (keep the version in a leaf module so the CLI graph never loads for a probe).

## Fleet Mapping (from the repo doc)

- `cron-format-standard` already conforms (Result: verdict, [SILENT] empty state, cost footer aggregate) — keep; add totals and truncation where evidence runs long.
- `cortex-doctor`: add `--toon` compact mode; truncate per-check detail with `--full`.
- `hc` CLI: TOON lists with totals; content-first home; structured errors on stdout.
- MCP servers (tasks, agent-bus): trim default schemas to id/title/status + totals.
- Ranked quick wins and the full surface-by-surface table live in
  `~/hermes-cortex/docs/axi-agent-ergonomics.md`.

## Pitfalls

- TOON is never a transport — bus/PGMQ bodies and MCP stay JSON; only stdout at the agent boundary converts.
- Retrofit high-frequency CLIs (hc, doctor) incrementally; big-bang rewrites break callers.
- A silently dropped flag is worse than an error: the agent gets plausible-looking output it trusts. Audit for `parse_known_args`-style silent drops.

## Verification

- Compare token count of old vs new output on a real sample.
- Ask: does the output answer the agent's next question without a follow-up call? If a follow-up is needed, pre-compute it or suggest the exact command (P4/P9).
