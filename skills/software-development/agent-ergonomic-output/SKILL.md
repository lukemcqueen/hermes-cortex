---
name: agent-ergonomic-output
description: "Use when building scripts whose stdout agents read (AXI)."
version: 1.0.0
category: software-development
platforms: [linux, macos]
aliases: [axi, axi-conventions, toon-output, agent-facing-output]
related_skills: [cron-format-standard, architecture-review, requirements-elicitation, change-checklist, adversarial-verifier, cron-output-contracts]
---

# Agent-Ergonomic Output (AXI)

## When to Use

Trigger on ANY of: creating or modifying a CLI script whose stdout an agent
consumes (fleet scripts, health checks, task lists, bus tooling); adding a
`--toon` mode; reviewing an output format; applying the AXI principles
(Agent eXperience Interface, by Kun Chen — MIT).

**The core insight:** the most expensive token cost is not a longer response
— it is the **follow-up call**. Every convention below exists to eliminate
one. Turns = LLM calls = the cost line.

## The 10 Principles (condensed)

| # | Principle | Rule |
|---|-----------|------|
| 1 | Token-efficient output | TOON-lite on stdout (`name[N]{fields}:` header + CSV rows), ~40% savings over JSON; JSON stays internal |
| 2 | Minimal default schemas | 3–4 fields per item (id, title, status); `--fields` escape hatch |
| 3 | Content truncation | Preview + `... (truncated, N chars total)` + `--full` hint; never silently omit |
| 4 | Pre-computed aggregates | `count: N of TOTAL`; derived statuses like `checks: 3/3 passed` |
| 5 | Definitive empty states | "0 results with context", exit 0; never bare empty output |
| 6 | Structured errors & exit codes | Errors on stdout in data format; exit 0 (incl. no-op) / 1 error / 2 usage; idempotent mutations; no prompts; fail loud on unknown flags |
| 7 | Ambient context | Session-start dashboard (≤15 lines, PII-safe); session-end capture (metadata only) |
| 8 | Content first | No-args shows live state, not help text |
| 9 | Contextual disclosure | 1–3 complete next-step commands, placeholders, flags carried forward; omit when self-contained |
| 10 | Consistent help | Per-subcommand `--help` (flags+defaults+2–3 examples); fast bare `--version` from a leaf module |

Full detail + examples: `references/axi-ten-principles.md`.

## Hard Rules in Hermes Cortex

1. **Protocol boundary:** bus wire format (PGMQ JSON) and MCP transport stay
   JSON — TOON is an output-boundary format ONLY, never a transport. Never
   convert a machine protocol to TOON.
2. **cron-format-standard is preserved** — it already encodes P4/P5 (`Result:`
   verdict, `[SILENT]` empty state, cost footer). Only add totals/truncation
   hints; never restructure it.
3. **Measured, never asserted:** stand up the token/turn telemetry baseline
   BEFORE any retrofit ("reduction" is a measured delta, not a claim — the
   owner rejects unverified numbers). Harness records integer counts only
   (never message/task content), metered out-of-band so it cannot inflate
   what it measures.
4. **Teach the static gates the format first:** adversarial-verify and
   secret-leak-detector must parse TOON before any TOON ships (golden
   fixture generated from the canonical emitter), or they false-block on
   example data or miss drift. This blocks all adoption until resolved.
5. **Redaction is mandatory, not optional:** shared emit_error()/truncate()
   paths strip tracebacks, paths, credentials, and PII (reuse
   secret-leak-detector patterns), backed by golden tests. Never string-
   interpolate untrusted data fields into suggested shell commands — use a
   shlex-quoted command builder (injection vector otherwise).
6. **Aggregates derived, never guessed:** `count == len(rows)`, TOTAL from
   the unfiltered query; contract test asserts it (verify-vs-original).
7. **Additive rollout:** ship `--toon`/`--full` flags beside existing output;
   rollback is a per-script revert. Never big-bang a format change.
8. **Conformance checks warn first:** new doctor checks ship as ⚠️, promote
   to ❌ only after a soak proving zero false positives; scope to registered
   agent-facing scripts so unrelated deploys are never gated.
9. **Deploy-sync safety:** any new shared lib registers in cortex-update.sh
   + a post-deploy import smoke test (`python3 -c 'import ...'` on the
   deployed path) so a partial deploy fails at deploy time, not at cron
   runtime.
10. **Role correctness:** output must never imply a non-orchestrator can
    install crons/daemons; gate such suggestions behind role checks.

## Adoption Workflow (proven order)

1. Telemetry baseline (F-022 pattern) — the "before" number.
2. Teach adversarial-verify + secret-leak-detector the new format.
3. Build the shared output lib (one deep module at the output boundary,
   e.g. `ops/scripts/lib/axi_out.py`) with full contract tests + boundary
   matrix (empty, 0, -1, None, non-ASCII, large N, oversized field) +
   golden-parity fixtures.
4. Retrofit top-N surfaces by invocation frequency; each gets a thin
   integration test asserting it routes through the shared lib.
5. Ambient context + disclosure engine (shlex-quoted, role-gated).
6. Enforcement: conformance lint → CI gate after soak; parse_known_args
   audit (no silent flag drops).
7. Verify the delta against baseline. If the metric doesn't move, STOP and
   re-plan — the metric is the point.

## Pitfalls

- **JSON-default verbosity:** a list tool emitting 10+ fields per item costs
  tokens × row count; default to id/title/status (real example: task lists
  emitting id, content, agent_name, status, session_id, priority, project,
  repo, scope, kind…).
- **Empty vs error:** a dead dependency (bus/DB/MCP down) must emit a
  structured error (exit 1), NEVER read as "0 results" (exit 0). Centralize
  this in the shared lib.
- **Silently dropped flags:** `parse_known_args` or ignored `--fields`
  values produce plausible-looking wrong data — worse than an error. Fail
  loud with the valid list + exit 2.
- **Version probes pulling the CLI graph:** `--version` is probed
  constantly; keep the version constant in a leaf module (stdlib-only
  imports) so the probe never loads the heavy command graph.
- **Suggestions that drop disambiguating flags** mislead agents worse than
  no suggestion; carry flags forward, use `<id>` placeholders.
- **The rearchitecture trap:** converting read-path MCP tools to CLIs and
  retiring JSON previews breaks cron JSON parsers and the 24/7 fleet
  consumers (protocol violation). If ever pursued: wrap-don't-replace,
  shadow/parallel mode, JSON preserved until consumers verified migrated,
  gated on telemetry proving that surface is the dominant cost.

## Verification

- Contract tests per emit function (header, count, empty phrasing, exit
  codes 0/1/2, stdout/stderr channel discipline).
- Golden-parity (known-answer) fixture pinning each surface's exact output
  shape — silent drift fails at CI.
- Assert error output contains no `Traceback`, no absolute path, no
  dependency-internal markers.
- Adversarial gate A2 (A4 for manage/quality/hooks/plugins); TDD RED→GREEN.

## Support Files

- `references/axi-ten-principles.md` — full distilled principles with TOON
  examples + the Cortex status-quo table (which surfaces already conform).
- `references/delegated-design-review.md` — recipe for running elicit +
  6-role party via delegated pro-model subagents when the user is absent.

## Pointers

- Public: `docs/axi-agent-ergonomics.md` (principle distillation, committed).
- Private: `docs/elicit/2026-08-24_axi-implementation.md`,
  `docs/design/2026-08-24-axi-implementation-decision.md` (party: Option B —
  shared axi_out.py layer — won 8.50 vs 4.25/5.75),
  `docs/plans/2026-08-24-axi-implementation.md` (phased implementation).
- AXI source: the AXI project (kunchenguid/axi, MIT) — TOON spec linked
  from its repo.
