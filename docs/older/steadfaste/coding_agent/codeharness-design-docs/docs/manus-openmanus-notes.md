# Manus / OpenManus — context & harness optimizations

Source: `manus.im` (closed product) + `FoundationAgents/OpenManus` (open
reimplementation, read from source). OpenManus is the reference for *how* Manus
achieves "95% autonomous task completion" — it is not the thing to fork (it's a
fast-moving demo-grade codebase), but the *patterns* are worth lifting.

## The one big idea: the plan is the context

Manus's central controller drafts a **plan** (via a `planning` tool call), then
dispatches each step to a **specialized sub-agent**. Crucially, each executor is
handed only:

```
CURRENT PLAN STATUS:
  ... tracked step list with [✓]/[→]/[ ] marks ...
YOUR CURRENT TASK:
  You are now working on step N: "..."
```

Not the whole conversation. Not the whole plan rationale. Just the tracked plan
status + the one step. This is the core context-management trick: **decompose
into a structured, tracked plan; each worker gets a narrow slice; the plan is
the shared memory, not the transcript.**

Maps to our frozen core: the core already knows `task_id` not "session". Manus
adds the worker-side discipline — a worker should emit `CHECKPOINT`/`PROGRESS`
per plan step and keep its own transcript small by design.

## Concrete harness optimizations to lift

| # | Pattern | Where in OpenManus | Why it matters for "boring, stable" |
|---|---------|--------------------|-------------------------------------|
| 1 | **`max_observe` truncation** | `toolcall.py` — every tool result sliced to `max_observe` chars before entering memory | Prevents one `cat`/grep of a large file from flooding the context window. Cheap, deterministic context budget. |
| 2 | **`max_steps` turn budget** | `base.py` — `current_step < max_steps` gate | Hard cap; the loop cannot run away. We already have this as `budget.max_turns`. |
| 3 | **Duplicate/stuck detection** | `base.py` `is_stuck()` — same assistant content repeated `duplicate_threshold` (2) times → inject "consider new strategies" prompt | Machine-checkable thrash-loop guard. Cheap version of our "no re-derivation" rule. |
| 4 | **TokenLimitExceeded → graceful FINISHED** | `toolcall.py` — catches the token error, records it, transitions to FINISHED | Failures are *states*, never crashes. Matches our "adapter never throws; failures are events". |
| 5 | **State machine + `state_context`** | `base.py` — IDLE→RUNNING→FINISHED/ERROR, revert on exception | Safe state transitions, no half-states. Matches the frozen task state machine. |
| 6 | **MCP as the tool extension boundary** | `manus.py` — tools added/removed at runtime via MCP servers, browser isolated via Browser Use MCP | Tools are peripheral and swappable — same discipline as "workers are peripheral". |
| 7 | **Sandbox as the execution boundary** | `app/sandbox` (Daytona) + browser in its own MCP | Maps directly to our frozen core's "workspace isolation". |
| 8 | **Plan as a typed tool** | `tool/planning.py` — `create/update/list/mark_step` with zod-style schema, statuses tracked | The plan is a structured, versioned object, not prose. This is what lets step 1 (narrow slices) work. |

## What NOT to take

- The framework's **release churn** — OpenManus is a prototype that moves fast.
- **Daytona / Linear / browser-operator specifics** — provider dependencies.
- **`ask_human` as a first-class loop tool** — good idea, but belongs in the
  worker layer, not the frozen ABI (keep the ABI small).
- The **`planning` tool's in-memory `plans: dict`** — not durable, not
  crash-safe. Our plan state, if tracked at all, must go through the atomic
  store (`src/store.ts`), not a process-local dict.

## What this changes in the harness design

The frozen core is unchanged (it never knew about sessions). The Manus borrows
land in the **worker layer**:

1. Worker decomposes objective → tracked plan (structured, per-step status).
2. Worker emits `PROGRESS`/`CHECKPOINT` per step boundary.
3. Worker truncates tool output to a `max_observe` budget before appending.
4. Worker detects duplicate turns and injects a strategy-change signal.
5. Worker treats token-limit as a terminal state (`FAILED` with reason), never
   a crash.

None of these require touching `abi.ts`. That is the test of the design: a
three-year-old worker can add Manus-style planning without a core change.
