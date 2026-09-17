# Reference implementations — what to steal, what to skip

Three open codebases define the current state of the art for coding-agent
harnesses. Read them shallow-cloned (`git clone --depth 1`), focus on the files
that define shape, not the README.

## Pi — `earendil-works/pi` (formerly `badlogic/pi-mono`)

Monorepo: `pi-ai` (provider layer), `pi-agent-core` (loop), `pi-coding-agent`
(CLI), `pi-tui`, `pi-protocol`, `chord`, telemetry.

**Read:** `packages/agent/src/agent-loop.ts` (the loop), `agent/src/types.ts`
(event vocab + tool contract), `protocol/src/protocol.ts` (ABI versioning),
`ai/src/index.ts` (provider layering), root `README.md` (supply-chain
section), `tui-plan.md` (alt-screen layout).

**Steal:** the loop shape (one `while`: stream → tools → append → repeat); the
event vocabulary (`agent_start/end`, `turn_start/end`, `message_*`,
`tool_execution_*`); the tool contract (TypeBox schema validation,
`prepareArguments`, `replay: never|safe`, `executionMode`); the
`PROTOCOL_VERSION` + `hello` handshake + `additionalProperties: false`; the
supply-chain discipline (pinned exact deps, lockfile-as-truth, shrinkwrap,
`min-release-age`, reviewed lifecycle-script allowlist).

**Skip:** `chord` (app-composition runtime), telemetry package, evals, the TUI
framework itself, server/client split. Too much surface.

**Why not adopt:** release philosophy explicitly permits breaking API changes in
minor releases; evolving fast.

## OpenSwarm — `Intrect-io/OpenSwarm`

TypeScript orchestrator (Claude Code / Codex / OpenRouter / local), Ink TUI,
SQLite run ledger, LanceDB memory, Linear/Discord.

**Read:** `src/taskState/store.ts` (atomic store — the gem), `src/tui/App.tsx`
+ `src/tui/panels/PipelinePanel.tsx` (cockpit), `src/orchestration/decisionEngine.ts`
+ `writeScope.ts` (admission control), `src/orchestration/workflow.ts` (DAG).

**Steal:** the atomic store pattern (write temp → fsync → atomic rename → dir
fsync, token-guarded O_EXCL lock, versioned zod schema — its comments are a
masterclass in failure-mode thinking: torn files, stale locks, pid-namespace
generation changes, ENOSPC); the TUI cockpit (tabs Chat/Pipeline/Logs/Monitor,
`ContextBar`/`TabBar`/`HelpBar`, a `PipelinePanel` subscribing to daemon SSE
rendering `StageTimeline`/`SubagentTree`/`LiveLog`); admission control
(`fileScope` write boundaries, dependency-readiness gating, priority ranking).

**Skip:** Linear/Discord/LanceDB integration, benchmark ladder, provider
specifics.

## OpenManus — `FoundationAgents/OpenManus` (the open Manus reimplementation)

Python, ReAct + ToolCall agents, PlanningFlow/PlanningTool, Daytona sandbox,
browser via Browser Use MCP.

**Read:** `app/agent/base.py` (state machine, max_steps, stuck detection),
`app/agent/toolcall.py` (max_observe, token-limit handling),
`app/flow/planning.py` + `app/tool/planning.py` (plan-as-context),
`app/agent/manus.py` (MCP boundary).

**Steal (the Manus core trick — plan is the context):** the controller drafts a
structured plan, dispatches each step to a specialized sub-agent that receives
only the plan status + its one step. Concrete context-budget levers, all
worker-layer:

- `max_observe` — truncate every tool result to a fixed char budget before it
  enters context.
- `max_steps` — hard turn budget; the loop cannot run away.
- duplicate-turn ("stuck") detection — same assistant content N times ⇒ inject a
  "try a new strategy" signal.
- token-limit ⇒ graceful terminal state, never a crash.
- state machine + `state_context` — IDLE→RUNNING→FINISHED/ERROR, revert on
  exception.
- MCP as the runtime tool-extension boundary; sandbox as the execution boundary.

**Skip:** the framework's release churn (fast-moving demo), Daytona/Linear
specifics, `ask_human` as a first-class loop tool (belongs in the worker layer,
not the frozen ABI), and the non-durable in-memory `plans` dict (plan state must
go through the atomic store).

## FrontierAgent — `ApodexAI/FrontierAgent` (the inference-aware one)

Python 3.12 agent runtime + TUI + benchmark suite; Apache-2.0. Deeper about
**real-token context management** than any of the above — this is the harness to
read when the loop keeps dying on context-limit provider 400s.

**Read:** `frontier_agent/core/runtime/loop/tiered_compact.py` (the crown
jewel), `_runaway.py`, `model_profile.py`, `tokenizer.py`,
`budget_consistency.py`, `../model_registry.yaml` (sibling),
`components/agent_bus/spawn_guard.py`, `components/observers/wall_clock_guard.py`,
`infra/providers.yaml` + `core/llm.py`. Every pattern below is a lesson, not a
library — copy the logic into your own loop.

**Steal — the inference-aware core (the gap our harnesses keep missing):**

- **Real-token gauge + scale-corrected compaction trigger.** Tiktoken cl100k
  understates real prompt tokens (~14%). Read the ACTUAL `prompt_tokens` from
  the last LLM response, compute `real/estimate`, clamp the scale, and project
  the size of the *next* request before deciding to compact. A raw ratio trigger
  (`max_len * 0.8`) alone is fatal on long loops: measured 51/51 sub-agents died
  one turn past the trigger (median 207,803 → 264,743 on a 209,715 limit) because
  one assistant turn's replayed reasoning adds 40k+ tokens. Trigger on the
  request about to be sent, never on the already-sent one.
- **Tiered compaction.** Try cheap candidates first (keep-last-N tool results →
  1200/600/300-char tool-result compression), reach for an LLM summary of the
  real history only when still over budget. Persist compacted evidence to disk
  (`spill_refs`) so summary omissions stay recoverable, and keep a rollback cache
  so a failed summary does not re-run every turn without freeing a token.
- **Reasoning-runaway detection.** DeepSeek/o-series-class models can burn the
  whole `max_tokens` inside the thinking channel and return a *successful* empty
  completion (`finish_reason=length`, no text, no tool call). Detect it, retry
  at a halved cap with a transient user-turn reminder, and never let the reminder
  enter durable history. Reasoning models will hit this — a plain retry-loop
  burns minutes per persisted runaway.
- **Non-blocking tokenizer.** Load tiktoken on a daemon thread; fall back to a
  CJK-aware heuristic (CJK char ≈ 1 token, Latin ≈ chars/4) until it loads. The
  loop must never block a turn on a tokenizer network fetch.
- **Budget-consistency startup check.** Warn loudly when `max_input + max_tokens
  > max_len` at profile load, so a misconfig surfaces as a named knob instead of a
  mid-run provider 400.
- **Data-driven thinking-format registry** (`model_registry.yaml`): regex the
  model id → `thinking_format` (deepseek→`reasoning_content`, anthropic→
  `content_block`, qwen→`tag`), editable without touching code, and never emit
  `reasoning_content` as a bare wire field except in the format that requires it
  (leak-guard on multi-turn replay).
- **Provider registry + fallback chain** (`providers.yaml`): name→provider map
  with env-expanded creds (`${VAR:-default}`), `model_chains`, a `FallbackLLM`
  wrapper — the same cheap-first + fallback model our cron provider chain uses.

**Steal — bounded parallelism (SpawnGuard + WallClockGuard):**

- **SpawnGuard's five layers:** depth, concurrency semaphore (queues, never
  rejects), token budget (pre-check at submit), wall-time, RAII reservation that
  auto-releases on exception/abort.
- **WallClockGuard — the fix for work lost to hard-cancel.** A soft deadline
  observer injects a *"stop and submit your report now"* message before the hard
  `asyncio.wait_for` cancels. Measured at 52.8% of sub-agents discarded as
  `(empty report)` by hard cancellation — the deadline turns a 30-turn sub-agent
  into a salvageable report instead of a lost failure.

**Steal — sandbox hardening:** environment **allowlist** (rebuild child env from
~30 named vars, never a denylist — impossible to enumerate every credential
name), per-exec cgroup v2 `memory.oom.group=1` (kill the offending tree, not the
host), tool-user uid drop so model code can't read `/proc/<harness-pid>/environ`,
manifest-based output gating (only declared publishers write deliverables),
head+tail `_CappedSink` at the pipe level so a large `cat` can't OOM the harness.

**Steal — the zero-cost telemetry seam** (`sdk_shim.py`): every external
observer/emitter/aggregator is a no-op shim reached through `metadata` keys, so
an external recording layer can bolt on without the workflows importing it. The
same pattern gives us a governance/heartbeat plugin seam with no core edits.

**Skip:** wrapping the whole framework as an SDK — its OpenAI-compatible
endpoint means the integration cost is one provider entry + a thinking-format
profile, not a library dependency. Don't vendor a second loop when the valuable
part is these token/context decisions.

**Why not adopt wholesale:** heavier than the others (27K lines, own TUI + eval
suite + benchmark runners); the portable value is the inference-aware patterns
above, not the framework.
