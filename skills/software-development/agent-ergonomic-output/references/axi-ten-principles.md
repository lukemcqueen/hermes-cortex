# AXI — The 10 Principles, Full Detail (distilled 2026-08-24)

Source: AXI (Agent eXperience Interface) by Kun Chen, MIT — the AXI website
and the kunchenguid/axi repo. Distillation committed at
`docs/axi-agent-ergonomics.md` (public repo).

The core insight: the most expensive token cost is not a longer response —
it is the **follow-up call**. AXI benchmark evidence (915 runs): AXI-wrapped
tools hit 100% success at the lowest cost, ~3 turns/task vs 6–8 for MCP, and
MCP costs ~2×. Fewer turns = fewer LLM calls = the cost lever.

## 1. Token-efficient output
TOON (Token-Oriented Object Notation) on stdout — ~40% token savings over
JSON, still readable. Convert at the output boundary; keep internal logic on
JSON.

```
tasks[2]{id,title,status,assignee}:
  "1",Fix auth bug,open,alice
  "2",Add pagination,closed,bob
```

## 2. Minimal default schemas
Every field costs tokens × row count. Default = identifier, title, status
(3–4 fields). Default limits high enough for one call. Long content belongs
in detail views. Offer `--fields`.

## 3. Content truncation
Never omit large fields entirely — preview + total size + escape hatch.

```
  body: First 500 chars of the issue body...
    ... (truncated, 8432 chars total)
help[1]: Run `tasks view 42 --full` to see complete body
```

## 4. Pre-computed aggregates
The expensive cost is the follow-up call. Include totals (`count: 30 of 847
total`) and derived statuses (`checks: 3/3 passed`) the backend can compute
cheaply — the summary, not the full data.

## 5. Definitive empty states
`tasks: 0 closed tasks found in this repository` — state the zero with
context. Ambiguous empty output makes agents re-run to verify.

## 6. Structured errors & exit codes
- Idempotent mutations: `task: #42 already closed (no-op)` — exit 0.
- Errors on stdout, same format as data, with an actionable suggestion;
  never leak raw dependency errors.
- No interactive prompts — flags alone complete every operation.
- Fail loud on unknown flags: reject by name, list valid flags, exit 2. A
  silently dropped flag yields plausible-looking WRONG data — the worst
  failure mode.
- Channels: stdout = data/errors; stderr = debug/progress; exit 0 (incl.
  no-ops) / 1 error / 2 usage.

## 7. Ambient context via session integrations
Session hook injects a compact live-state dashboard at session start
(explicit opt-in, idempotent, directory-scoped, ruthlessly minimal — it
loads EVERY session). Session-end hooks capture what happened so the next
start gets richer. A static skill is the secondary, on-demand path; keep the
two in sync (single source of truth + a `--check` CI step).

## 8. Content first
No-args shows the most relevant live content, not usage:

```
$ tasks
tasks[3]{id,title,status}:
  1,Fix auth bug,open
help[2]:
  Run `tasks view <id>` to see full details
  Run `tasks create --title "..."` to add a task
```

## 9. Contextual disclosure
After list/mutation output, 1–3 complete next-step commands carrying forward
disambiguating flags, `<id>` placeholders for runtime values. Omit when the
output is self-contained. On errors, suggest the specific fixing command,
not "see --help".

## 10. Consistent help + fast --version
Home view identifies the tool (path + one-line description). Per-subcommand
`--help`: flags with defaults, required args, 2–3 examples, scoped. `-v`/
`-V`/`--version` print the bare version and exit 0 fast — keep the version
constant in a leaf module (stdlib-only imports) so the heavy CLI graph never
loads for a probe.

---

## Cortex status quo (as of 2026-08-24)

| Surface | Already conforms | Gaps |
|---|---|---|
| Cron deliveries (`cron-format-standard`) | `Result:` verdict; `[SILENT]` empty state; cost footer (P5/P4) | No size hints/truncation; lists rarely carry totals |
| `cortex-doctor` | Per-check statuses; remediation hints (P9); content-first (P8) | Prose-only; no `--toon`; detail not truncated with `--full` |
| `hc` CLI | "No pending messages" (P5); REFUSED-with-next-steps (P9); refuses prompts (P6) | Emoji prose on stderr; usage-first home (P8); no TOON lists (P1/P2) |
| MCP tool outputs | JSON protocol-correct | Verbose fields (P2); totals missing (P4); bare `[]` empties (P5) |
| Bus bodies (PGMQ JSON) | Machine protocol — fine as-is | Previews are where P1–P5 apply |
| task-db.py, adversarial-verify.py, health scripts | Varying | Prose/JSON mix, no shared convention |

Real violation example (task-db.py `pending`): raw JSON with 10+ fields per
item — id, content, agent_name, status, session_id, priority, project, repo,
scope, kind — and no totals. Textbook P2+P4 target.

## The "TOON-lite" convention (adopted for Cortex)

`name[N]{fields}:` header line + one CSV row per item + a `count: N of
TOTAL` line. JSON stays inside scripts and in machine protocols (bus, MCP).
If a full TOON library is overkill, the header+CSV shape is the minimum that
agents parse cheaply.
