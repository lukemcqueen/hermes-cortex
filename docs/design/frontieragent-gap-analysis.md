# FrontierAgent Gap Analysis → Hermes Cortex

**Status:** Recommendations | **Scope:** public framework doc — inference-aware runtime, bounded orchestration, sandbox safety, SDK interface lessons
**Source analyzed:** `ApodexAI/FrontierAgent` (Apache-2.0, ~27K lines Python), commit 2026-09-14
**Owner:** Esther | **Related:** `docs/env-vars.md` (provider/fallback model), `docs/design/`

---

## What FrontierAgent is

Apache-2.0 agent runtime + TUI + evaluation suite by Apodex. `pip install frontier-agent`
exposes `LLMClient` / `LLMResponse` / `StreamDelta` protocol contracts and a
`run_agent_loop` kernel. Four strict layers:

| Layer | Contents |
|-------|----------|
| `frontier_agent/` | generic loop, scheduling, registries, AgentBus, observers |
| `plugins/tools/` | tool implementations + sandbox policy |
| `workflows/` | ReAct + Agent Team pipeline specs, profiles, prompts |
| `benchmarks/` | public eval harness + bundled benchmarks |

Its endpoint is OpenAI-compatible (`/v1`), so integration effort is one provider entry
+ a model profile — not a full SDK wrapper.

---

## The gaps worth filling (prioritized)

### 1. Inference-aware context management — the big one

FrontierAgent calibrates its runtime to **real served tokens**, not estimates:

- **Real-token gauge + scale-corrected trigger** (`tiered_compact.py`). Reads actual
  `prompt_tokens` from the last LLM response, computes `real/estimate` scale
  (tiktoken cl100k understates ~14%), and projects the *next* request before
  triggering compaction. A raw 0.8-ratio trigger alone killed 51/51 sub-agents —
  each crossed the hard context ceiling by one turn (median 207,803 → 264,743 on a
  209,715 trigger). Our compaction has no such real-token guard.
- **Tiered compaction** (`tiered_compact.py`): keep-last-N tool results → cheap
  1200/600/300 char-compression candidates → LLM-summarize real history only as last
  resort, with spill-to-disk recovery (`spill_refs`) so compacted evidence stays
  recoverable. Rollback-cache stops a failed summary re-running every turn.
- **Reasoning-runaway detection** (`_runaway.py`): logic models that burn `max_tokens`
  inside thinking and return a *successful* empty completion (`finish_reason=length`,
  no text, no tool call) → retry at a halved cap with a transient user-turn reminder
  that never enters durable history. Plus `reasoning_only_timeout_s` /
  `reasoning_only_max_tokens` streaming watchdog (`workflows/agent_team/README.md`).
- **Non-blocking tokenizer** (`tokenizer.py`): tiktoken loads on a daemon thread, CJK-aware
  heuristic fallback so the loop never blocks on a network fetch.
- **Config-budget consistency check** (`budget_consistency.py`): startup warnings when
  `max_input + max_tokens > max_len` — surfaces a misconfig as a named knob instead of a
  mid-run provider HTTP 400.

### 2. Bounded parallel orchestration

`SpawnGuard` (`spawn_guard.py`) — five layers: depth, concurrency semaphore (queues,
never rejects), token budget (pre-check), wall-time, RAII reservation.

The standout: a soft `WallClockGuard` injects a *"stop and submit your report now"*
message **before** the hard `asyncio.wait_for` cancels — measured fix for 52.8% of
sub-agents formerly discarded as `(empty report)` (`bus.py:96-122`,
`observers/wall_clock_guard.py`). Plus a `MessageTrimmer` collapses completed task
boundaries to `[prompt, final_report]` so a reused multi-task sub-agent keeps
task-level memory without token blowup (`message_trimmer.py`).

### 3. Sandbox safety

- **Environment allowlist, not denylist** — child env rebuilt from ~30 named vars so
  `DATABASE_URL` / Kubernetes-injected secrets can't sneak in.
- **Per-exec cgroup v2** `memory.max` + `memory.oom.group=1` — kills the offending tree,
  not the whole host.
- **Tool-user uid drop** so model code can't read `/proc/<harness-pid>/environ`.
- **Manifest-based output gating** — only declared publishers write `/outputs`; denials
  escalate to the coordinator for re-dispatch.
- **CappedSink** head+tail retention at the pipe-read level — no OOM on a huge `cat`.

### 4. SDK / interface extension point

`sdk_shim.py` shows their "SDK" as a **no-op shim** where an external protocol +
telemetry layer bolts on via `metadata` keys (`sdk_extra_observers`,
`sdk_protocol_emitter`, `sdk_protocol_usage_aggregator`) — heartbeat, per-worker
traces, cross-agent usage aggregator. Everything degrades to no-op without it: a
zero-cost telemetry seam pattern worth mirroring for our governance/heartbeat.

---

## Recommended actions for us (cheap → valuable, in order)

1. **Add an `apodex` provider entry + a model-profile thinking-format table**
   (mirroring `providers.yaml` we already have, plus a `model_registry.yaml`-style
   `thinking_format` table: `deepseek → reasoning_content`, `anthropic → content_block`,
   `qwen → tag`) so we can call the endpoint and correctly parse `reasoning_content`.
   Small, immediate.
2. **Real-token gauge → compaction trigger** in our loop. Our single biggest inference
   blind spot; FrontierAgent's fix is proven and directly portable.
3. **Adopt `_runaway.py`** detection (capped-empty completion resample) — we run reasoning
   models and can hit this today.
4. **`WallClockGuard` before hard-cancel** in our sub-agent delegation path — saves real
   work that a timeout would discard.
5. **Copy the zero-cost telemetry seam** (`sdk_shim` pattern) so our governance/heartbeat
   plug in without core edits.

---

## Caveats

- **Don't wrap their whole SDK** — that would duplicate `hermes-agent`'s loop. The
  practical integration is provider + model profile.
- Recommendation is **forward-looking, not an ADR** — each item should become its own
  task/decision before implementation.
- Two of the first survey fan-out sub-agents hit an OpenRouter 402 credit wall mid-run;
  the orchestration and interface areas were re-verified by direct repo reads, so the
  analysis above reflects the actual code, not summaries.