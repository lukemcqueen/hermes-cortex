# AXI Principles for Hermes Cortex — Agent-Ergonomic Output

> Distilled from the AXI project (Agent eXperience Interface, by Kun Chen,
> MIT — the AXI website and the AXI skill in the
> [kunchenguid/axi](https://github.com/kunchenguid/axi) repo) — 2026-08-24.
> This is framework guidance: apply it to every surface an agent reads.
> The most expensive token cost is not a longer response — it is the
> **follow-up call**. Every principle below exists to eliminate one.

## What AXI is

AXI ("Agent eXperience Interface") is a set of 10 design principles for
building CLI tools that autonomous agents use via shell execution. It
treats **token budget as a first-class constraint**. Its reference
implementations (`gh-axi`, `chrome-devtools-axi`) wrap existing tools
(`gh`, chrome-devtools-mcp) and re-emit their output in a token-lean,
decision-ready format.

Evidence (published, 915 runs, Claude Sonnet 4.6):

- GitHub: `gh-axi` **100% success**, **$0.050/task**, 3 turns, 15.7s —
  vs `gh` CLI 86%/3 turns and GitHub MCP 87%/$0.148/6 turns.
- Browser: `chrome-devtools-axi` 100%/$0.074/4.5 turns vs MCP variants
  99–100%/$0.091–$0.120/6.2–7.6 turns.

Read: MCP costs ~2× a good CLI in both dollars and turns. **Fewer turns is
the lever** — turns are LLM calls, and calls are the cost line.

The output format used is **TOON** (Token-Oriented Object Notation, spec
linked from the AXI repo) — ~40% token savings over equivalent JSON while
staying readable. Internal logic stays JSON; conversion happens only at the
output boundary.

## The 10 Principles — Distilled

### 1. Token-efficient output
Emit TOON on stdout, not JSON. Convert at the output boundary; keep internal
logic on JSON.

```
tasks[2]{id,title,status,assignee}:
  "1",Fix auth bug,open,alice
  "2",Add pagination,closed,bob
```

### 2. Minimal default schemas
Every field costs tokens × row count. Default to the smallest schema that
lets the agent decide the next step: identifier, title, status. 3–4 fields,
not 10+. Offer `--fields` to request more. Default limits high enough to
cover common cases in one call.

### 3. Content truncation
Never omit a large field entirely; include a truncated preview with the
total size and the escape hatch.

```
  body: First 500 chars of the issue body...
    ... (truncated, 8432 chars total)
help[1]: Run `tasks view 42 --full` to see complete body
```

### 4. Pre-computed aggregates
The expensive cost is the follow-up call. Compute what agents commonly need
next and include it: **total counts** (`count: 30 of 847 total`) so agents
don't paginate to learn "how many", and **derived status fields**
(`checks: 3/3 passed`) — the summary, not the full data.

### 5. Definitive empty states
When the answer is "nothing", say so explicitly. Ambiguous empty output
makes agents re-run with different flags to verify. `tasks: 0 closed tasks
found in this repository` — state the zero with context.

### 6. Structured errors & exit codes
- **Idempotent mutations** — closing an already-closed item is exit 0
  (`task: #42 already closed (no-op)`), not an error.
- **Structured errors on stdout** in the same format as normal output, with
  an actionable suggestion. Never leak raw dependency errors.
- **No interactive prompts** — every operation completable with flags alone;
  missing required value = fail fast with a clear error.
- **Fail loud on unknown flags** — reject by name, list valid flags, exit 2.
  A silently dropped flag yields plausible-looking wrong data — the worst
  failure mode.
- Channels: stdout = structured data/errors; stderr = progress/debug;
  exit codes 0 success (incl. no-ops) / 1 error / 2 usage error.

### 7. Ambient context via session integrations
Register into the agent's session lifecycle so every session starts with
relevant live state visible — before any action. A session hook injects a
compact dashboard; an installable skill is the secondary, on-demand path.
Rules: explicit opt-in from a setup command, idempotent, directory-scoped,
**ruthlessly minimal** (it loads every session), and session-end hooks
capture what happened so the next start gets richer.

### 8. Content first
Running with no arguments shows the most relevant **live content**, not a
usage manual. Help text forces a second call; live state lets the agent act.

```
$ tasks
tasks[3]{id,title,status}:
  1,Fix auth bug,open
help[2]:
  Run `tasks view <id>` to see full details
  Run `tasks create --title "..."` to add a task
```

### 9. Contextual disclosure
End output with a few next steps that follow logically: after an open item →
suggest closing; after an empty list → suggest creating; after a list →
suggest viewing. Every suggestion is a complete command carrying forward
disambiguating flags, with `<id>` placeholders for runtime values. Omit when
the output is self-contained. On errors, suggest the specific fixing command,
not "see --help".

### 10. Consistent way to get help
Home view identifies the tool (path + one-line description). Every subcommand
supports `--help` — concise, complete: flags with defaults, required args,
2–3 examples, scoped to that subcommand. `-v`/`-V`/`--version` print the bare
version and exit 0 **fast** (probed constantly; latency is an ergonomics
property — keep the version in a leaf module so the heavy CLI graph never
loads for a version probe).

## Hermes Cortex status quo

| Surface | Already conforms | Gaps |
|---|---|---|
| Cron deliveries (`cron-format-standard`) | Definitive `Result:` verdict; `[SILENT]` empty state (P5); concrete-example prompts; cost footer aggregate (P4) | No size hints/truncation for long evidence; `Result:` is a verdict but lists rarely carry totals |
| `cortex-doctor` | Statuses per check (✅/❌/⚠️); remediation hints per check (P9); runs content-first with no args (P8) | Human-styled prose; no `--toon`/compact mode; per-check detail not truncated with `--full` |
| `hc` CLI (bus ops) | Definitive "No pending messages" (P5); REFUSED errors include next steps (P9); refuses rather than prompts (P6) | Emoji/human prose on stderr (P6 channels); usage text instead of content-first home (P8); no TOON lists (P1/P2); multi-line help not per-subcommand `--help` blocks (P10) |
| MCP tool outputs (agent-bus, tasks, loop-governance) | JSON is protocol-correct | Verbose field sets (P2); totals not always present (P4); empty results sometimes bare `[]` (P5) |
| Bus message bodies (PGMQ JSON) | Double-encoded JSON handled via `(body#>>'{}')::jsonb` — machine protocol, fine as-is | Agents read previews — previews are where P1–P5 apply, not the wire format |
| `task-db.py`, `adversarial-verify.py`, health scripts | Varying | Inconsistent: some prose, some JSON, no shared convention |

**Already strong:** the fleet's cron output standard and the doctor's
remediation hints are effectively AXI P5/P9 ahead of the curve. The gap is
consistency across *other* agent-facing surfaces.

## Principle → Improvement mapping

### P1+P2 — TOON lists, minimal schemas (HIGH, biggest cost lever)
- **New convention:** agent-facing CLI scripts emit TOON (or "TOON-lite":
  `name[N]{fields}:` header + CSV rows) for list/detail output; JSON stays
  inside scripts and in machine protocols (bus, MCP).
- `hc peek/list_queues`: replace emoji prose lists with `queue[3]{name,depth}`.
- MCP servers (tasks, agent-bus): trim default schemas to id/title/status +
  totals; add `--fields`-style verbosity only when requested.

### P3 — Truncation with escape hatch
- Long bodies (bus message previews, doctor detail, task descriptions):
  truncate at 500–1500 chars, show `... (truncated, N chars total)` and the
  `--full` command. `hc peek` already previews — add the size hint.

### P4 — Pre-computed aggregates
- List outputs carry `count: N of TOTAL` so agents never paginate to count.
- Doctor summary line already aggregates — extend the same pattern to
  `hc list_queues` (total pending across queues) and task lists (open vs
  blocked counts).
- Derived statuses where cheap: `checks: 3/3 passed` style summaries instead
  of raw fields the agent would have to interpret.

### P5 — Definitive empty states
- Standardize on "0 results with context" phrasing. `[SILENT]` in cron
  format already means "nothing to report" — keep it; make sure scripts that
  output `[]` or nothing say `queue: 0 messages` instead.

### P6 — Structured errors & exit codes
- Fleet scripts: errors on stdout in the same format as data, with an
  actionable suggestion; stderr reserved for debug/progress.
- Exit codes: 0 success (incl. idempotent no-ops), 1 error, 2 usage.
- Mutations idempotent: repeated sends/updates acknowledge no-op with exit 0.
- Fail loud on unknown flags (argparse defaults already do this — audit for
  any `parse_known_args` that silently drops flags).
- Never prompt interactively; `hc` already REFUSES instead of prompting —
  the pattern to keep.

### P7 — Ambient context (MEDIUM, orchestrator leverage)
- Hermes already has session-start injection (skills, memory, task-db
  restore). Add a **compact session-start dashboard** for orchestrators:
  pending tasks, inbox depth, doctor summary — TOON, ≤15 lines, and a
  session-end capture (auto-save-sessions already exists — the loop can
  close).
- Crons already inject prior output via `continuity`/`context_from` — that
  IS ambient context; keep it ruthlessly minimal per P7's token-budget rule.

### P8 — Content first
- `hc` with no args should show live fleet state (queue depths, pending
  messages) not usage. `--help` stays explicit. Doctor already runs
  content-first — the model to copy.

### P9 — Contextual disclosure
- Doctor remediation hints are the fleet's best example — already suggests
  the fixing command. Extend: after every list/mutation output, 1–3 complete
  next-step commands with placeholders, carrying forward the current flags.
- Omit suggestions on self-contained outputs (confirmations, counts).

### P10 — Consistent help + fast --version
- Every fleet CLI: per-subcommand `--help` (flags + defaults, 2–3 examples),
  `-v`/`-V`/`--version` bare version exit 0. Python scripts: keep the
  version constant in a leaf module (avoids importing the whole CLI graph on
  a probe).

## Ranked quick wins

1. **`hc list_queues` + `peek` → TOON with totals** (P1/P2/P4) — highest
   frequency agent-facing CLI; direct token + turn savings.
2. **MCP default-schema trim** on tasks/agent-bus list tools (P2/P4) — every
   fleet agent reads these; fewer fields × many reads.
3. **Doctor `--toon` compact mode** (P1/P2/P8) — keeps human mode, gives
   agents a lean machine-readable pass.
4. **Session-start orchestrator dashboard** (P7) — kills the "what's
   pending?" probe turn at session start.
5. **Truncation convention** in bus previews and doctor detail (P3).
6. **Structured-error pass** on the top 10 fleet scripts (P6) — stdout
   errors + exit codes 0/1/2 + no silent flag drops.

## Adoption rules of thumb

- **Machine protocol** (bus wire format, MCP transport): stays JSON — TOON is
  an output-boundary format, never a transport.
- **Agent-facing CLI stdout**: TOON preferred for new scripts; retrofit
  high-frequency ones (hc, doctor) incrementally.
- **Cron deliveries**: keep `cron-format-standard` (already AXI-aligned);
  add totals and truncation hints where evidence runs long.
- **Human-facing output** (user chat replies): unchanged — AXI governs
  agent-consumed surfaces, not conversation.
- Reference implementations to study: `gh-axi`, `chrome-devtools-axi`
  (official); `jj-axi`, `pg-axi`, `obsidian-axi` (community) — all in the
  [kunchenguid/axi](https://github.com/kunchenguid/axi) repo.
