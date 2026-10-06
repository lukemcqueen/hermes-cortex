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

## CLIs that OTHER AGENTS integrate with (not just read)

The principles above optimize for an agent *reading* stdout. A second case:
a harness — Pi, aider, a CI job, a shell script — must *call* your CLI because it
cannot speak your native protocol (no MCP client, no plugin API). Design for that
explicitly:

1. **Publish a manifest, not a per-agent binding.** `--tools-json` emitting the
   tool names, descriptions, input schemas, entrypoint shape and exit codes lets
   ANY harness, in any language, generate its own thin shim. One manifest beats
   N hand-written bindings that drift apart.
2. **Discover the surface at runtime; never hand-write a route table.** Mapping
   `<tool>` to a handler and enumerating the tool list from the implementation
   means a newly added capability is reachable automatically. A route list
   maintained beside the implementation is a second definition of the same thing
   and it drifts silently — a tool advertised with no handler is a dead entry an
   agent will call and fail on. Assert the invariant in a test.
3. **Separate a checking exit code from a failure.** Generalize principle 6:
   `0` ran/allowed, `1` ran but the operation was REFUSED (a decision — a caller
   gating on the code must see it), `2` usage error, `3` the dependency is
   unavailable. Collapsing a refusal into 0 is the damaging case: an automation
   that gates on the exit code concludes the guarded thing was free when it was
   locked. Give each meaning its own number and document them in the manifest.
4. **Keep the core importable without the optional protocol dependency.** Guard
   the import and degrade, rather than exiting at import time: the handlers are
   usually protocol-independent, so an import-time exit makes the capability
   unreachable from exactly the hosts that need the adapter. Only the server/
   transport entrypoint should refuse when the dependency is missing.
5. **Suppress the server's log configuration in CLI mode.** A module tuned for
   serving (e.g. `logging.basicConfig(level=DEBUG, force=True)` at import) floods
   stderr and buries the answer for a caller parsing output. Re-apply a quiet
   level after import, since `force=True` wins otherwise.
6. **Never fall back to a second implementation on failure.** Fail-open is for
   availability ("carry on with the feature"); it is never a license to
   re-implement the semantics locally. Report the dependency as unavailable
   instead — a fallback copy is how two implementations start.

Sibling rule for the adapter side: one implementation, per-host adapters that add
no semantics — see the `cross-agent-design` skill.

## Child processes: non-interactive, and out of the prompt area

When a harness, extension or script SHELLS OUT to another CLI, two rules apply to the
child, not to your own stdout:

1. **Pass the child's non-interactive flag; never let it prompt.** A password/passphrase
   prompt is written to `/dev/tty`, not to stdout/stderr — so a capture sees nothing, and
   the caller does not fail, it HANGS until a timeout (or forever), after which a
   fail-open contract reports "dependency unavailable" for what is really a missing
   credential. Give every child its flag: `psql -w` (`--no-password`), `ssh -o
   BatchMode=yes`, `git -c core.askpass=`, `ssh-keygen -N ""`, `apt-get -y`, package
   managers' `--yes`. Verify with the real binary and no credentials: it must exit
   non-zero FAST with a named error. A test that only asserts the flag is in the argv is
   necessary but not sufficient — exercise the runtime path once with the flag and once
   against a stand-in that honours the documented flag contract (prompt-path stub = a
   hang) when no server is reachable.
2. **A TUI harness's stderr IS the user's prompt area.** Routine diagnostics written
   there scribble over the input line. Route them to a BOUNDED log file under the
   cortex tree (`~/.hermes-cortex/logs/<component>.log`, mode 0600, rotate to `<log>.1`
   at a size cap) — the same shape `mcp-servers/loop-gov-mcp.py` uses — with the whole
   write wrapped so a logging failure can never change what the tool does. Keep GENUINE
   failures LOUD on stderr (a silent failure reads as "the feature had no data", a
   different and wrong conclusion) and also record them, since stderr is ephemeral;
   gate an echo-to-stderr behind a `*_DEBUG=1` env var so live debugging stays possible.
3. **Assert "child output does not leak" at the FD level in the PARENT.** `execFile`
   pipes stdio by default, so a child's stderr never reaches the parent's stderr — and
   patching the parent's stderr write in-process cannot see a write that bypasses it (an
   inherited fd). Capture the child process's real stderr and assert on that, and prove
   the check non-vacuous with a variant that DOES leak.

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
