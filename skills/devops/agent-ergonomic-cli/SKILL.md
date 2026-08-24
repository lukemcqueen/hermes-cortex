---
name: agent-ergonomic-cli
description: "Use when writing or auditing agent-facing CLI output."
version: 1.0.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cli, output, token-efficiency, toon, axi, agent-ergonomics, agent-facing]
    related_skills: [shell-scripting, cron-format-standard, change-checklist, unified-cli-script]
---

# Agent-Ergonomic CLI — AXI Output Principles

Design CLI/script stdout for the agents that consume it. Distilled from the
AXI project (Agent eXperience Interface, Kun Chen, MIT — 2026-08-24). Full
Cortex-surface mapping lives in `~/hermes-cortex/docs/axi-agent-ergonomics.md`.

## When to use

- Writing or modifying any script/CLI whose stdout an agent reads: fleet
  scripts, `hc`-style CLIs, doctor/health output, task lists, previews.
- Auditing agent-facing output for token bloat or missing decision data.
- Reviewing a change that emits lists, statuses, errors, or help text.

## Core insight

The most expensive token cost is **not a longer response — it's the
follow-up call**. An agent that must paginate to count, re-run to verify an
empty result, or read help to learn the next flag burns a second LLM call.
Published AXI benchmarks (915 runs): AXI-wrapped tools = 100% success at the
lowest cost, ~3 turns/task vs 6–8 for MCP; MCP costs ~2× a good CLI.

## The 10 principles (condensed)

1. **Token-efficient output** — TOON on stdout, JSON only internally.
   Convert at the output boundary.
2. **Minimal default schemas** — 3–4 fields per list item (id, title,
   status), not 10+. Offer `--fields` for more. Default limits that cover
   common cases in one call.
3. **Content truncation** — never omit a large field; show a truncated
   preview + total size + escape hatch (`--full`).
4. **Pre-computed aggregates** — totals (`count: 30 of 847 total`) so agents
   don't paginate to count; derived statuses (`checks: 3/3 passed`).
5. **Definitive empty states** — say `0 results` with context; bare empty
   output makes agents re-run to verify.
6. **Structured errors & exit codes** — errors on stdout in the same format
   as data with an actionable suggestion; stderr = debug/progress only;
   exit 0 success (incl. idempotent no-ops) / 1 error / 2 usage; no
   interactive prompts; fail loud on unknown flags (exit 2) — a silently
   dropped flag yields confident wrong action.
7. **Ambient context** — session-start integration shows live state before
   any action; ruthlessly minimal (loads every session); session-end
   capture enriches the next start.
8. **Content first** — no-args shows live data, not help text.
9. **Contextual disclosure** — 1–3 complete next-step commands after
   list/mutation output, carrying forward disambiguating flags, `<id>`
   placeholders for runtime values; omit when output is self-contained;
   on errors suggest the fixing command, not "see --help".
10. **Consistent help** — per-subcommand `--help` (flags + defaults, 2–3
    examples); `-v`/`-V`/`--version` prints bare version fast (leaf module,
    heavy graph never loads for a probe).

## TOON-lite cheat sheet

```
tasks[2]{id,title,status}:
  1,Fix auth bug,open
  2,Add pagination,closed
count: 30 of 847 total
help[2]:
  Run `tasks view <id>` for details
  Run `tasks create --title "..."` to add

task:
  number: 42
  body: First 500 chars...
    ... (truncated, 8432 chars total)
help[1]: Run `tasks view 42 --full` for complete body

error: --title is required
help: tasks create --title "..." [--body "..."]
```

## When NOT to apply

- **Machine protocol** (bus wire format, MCP transport): stays JSON — TOON
  is an output-boundary format, never a transport.
- **Cron deliveries**: follow `cron-format-standard` (already AXI-aligned:
  `Result:` verdict, `[SILENT]` empty state, cost footer).
- **Human chat replies**: unchanged — AXI governs agent-consumed surfaces.

## Cortex retrofit quick map (priority order)

1. `hc` list/peek → TOON with totals (highest-frequency agent CLI)
2. MCP list tools (tasks, agent-bus) → trim default schemas + totals
3. Doctor → `--toon` compact mode (keep human mode)
4. Session-start orchestrator dashboard (ambient context, ≤15 lines)
5. Truncation convention in bus previews (`... (truncated, N chars)`)
6. Structured-error pass on top fleet scripts (stdout errors, 0/1/2)

## Verification checklist

- [ ] Empty state says the zero with context (`queue: 0 messages`)
- [ ] Lists carry totals (`count: N of TOTAL`) — no pagination to count
- [ ] Truncated fields show size + `--full` escape
- [ ] Errors on stdout in data format, actionable suggestion, exit 0/1/2
- [ ] Unknown flags rejected by name with valid-flag list (exit 2)
- [ ] Mutations idempotent (repeat = exit 0 no-op, acknowledged)
- [ ] No interactive prompts — completable with flags alone
- [ ] Next-step suggestions are complete commands with placeholders
- [ ] `--help` per subcommand; `--version` bare + fast

## Sources

- Full distillation + Cortex mapping: `~/hermes-cortex/docs/axi-agent-ergonomics.md`
- Benchmarks + catalog: `references/axi-source-notes.md`
- Original: AXI by Kun Chen (MIT) — github.com/kunchenguid/axi
