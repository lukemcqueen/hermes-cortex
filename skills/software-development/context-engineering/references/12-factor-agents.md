# Dex Horthy — 12-Factor Agents: condensed verified research

Source: https://github.com/humanlayer/12-factor-agents (README + content/factor-*.md + appendix-13-pre-fetch.md), verified by Esther 2026-08-24 against the primary source (Moses' handoff summary checked out). Video: David Ondrej podcast with Dex Horthy (HumanLayer founder, "12 Factor Agents" author, ran a 4-month unattended agent software factory).

## The 13 factors (one-liners)

- **F1** — Natural language → tool calls (NL is the input, tools are the output).
- **F2** — Own your prompts (they're the product; version them like code).
- **F3** — Own your context window (the ONLY primitive: tokens in → tokens out; compact at ~50% "dumb zone", own the format, information density > message shape).
- **F4** — Tools are structured outputs (a tool call IS a structured output; always-output-JSON + declare intent in NL tokens is a valid alternative to "proper" tools).
- **F5** — Unify execution state + business state (one durable record).
- **F6** — Launch/pause/resume with simple APIs (durable, introspectable).
- **F7** — Contact humans with tool calls (`request_human_input`: urgency/format/choices) → outer-loop agents, durable pause/resume.
- **F8** — Own your control flow (deterministic switch/loop, not "prompt and pray").
- **F9** — Compact errors into context (≤3 consecutive retries, then escalate to a human — error counter reset on success).
- **F10** — Small, focused agents (3–10, maybe 20 steps max; as context grows LLMs lose focus; scope grows only as windows improve).
- **F11** — Trigger from anywhere (cron, webhook, chat — meet users where they are).
- **F12** — Stateless reducer (event list → prompt, replayable).
- **F13** — Pre-fetch all context you might need (DETERMINISTICALLY call the tools you know you'll want, include their outputs in context; let the model do the hard part of USING them, not FETCHING them).

## Key video points (software-factory model)

1. **Code review/trust is the bottleneck**, not build speed — build is minutes now.
2. **"PRs are dead" is half-true**: small changes ship straight to prod when the prompt is trusted; BUT their no-code-reading "light factory" FAILED (July 2025) — a bug no model could solve, weeks of slop. **You WILL read code again; stay in the loop.**
3. **Program design is the most-skipped step**: product spec → system architecture → program design (call stack, file placement, types + method signatures, NO bodies) → vertical slices (end-to-end thin slice first, test along the way).
4. **Measurable output = leverage**: "If you can tell it a measurable output, the agent will move mountains." Deterministic back-pressure beats vibes.
5. **Benchmarks don't measure maintainability** (one-off problems, no slop penalty). Novel check: **remove the model's patch, run its tests against pre-patch code — if they don't fail, the tests test nothing.**
6. **Context engineering is physics**: compact at ~50% (dumb zone), own the format, pre-fetch deterministically (free CPU ≠ inference tokens).
7. **Put everything in the codebase**: docs/adr/ + docs/external/ as clear markdown the model can read — don't spend tokens on "how to get context".
8. **Contact humans with tool calls** (structured request_human_input), not prose.
9. **The Goal (Goldratt)**: inefficiencies ≠ bottlenecks. Optimize the actual bottleneck.

## Hermes Cortex implementation (2026-08-24, committed)

- `ops/scripts/executor_context_builder.py` + `mcp-servers/executor-mcp.py` — **F13 pre-fetch**: `execution_request` builds the context envelope deterministically before dispatch (repo rules AGENTS/CLAUDE, slice plan, task, recent git history, worktree diff; budget-capped ~6000 chars). Coding agents spend zero tool round-trips fetching context. Tests: `tests/test_executor_context_builder.py` (6/6).
- `software-factory` skill — the 4-gate workflow (Product → Architecture → Program Design → Vertical Slices).
- `docs/adr/` — durable fleet decisions (0001 model contract + pricing, 0002 MAX_COST guard, 0003 bus v2 API), convention README + TEMPLATE.
- `docs/external/` — env var NAME registry (never values) + external services.
- `pre-commit-score` pass-rate measurement: real, monorepo-aware (discovery to depth 3, per-repo `ops/scripts/test-command.sh` opt-in, errors counted as failures, warn on incomplete measurement, fail-open only with no test infra).

## Already strong in HC (no action)

F2 (SOUL/AGENTS/skills prompts), F4/F8 (loop-governance, enforcer, adversarial verify, pre-commit gates), F6/F11 (cron + bus ecosystem), F9 (auto-remediation), F10 (60+ focused crons), F5 (task-db), cost tracking.
