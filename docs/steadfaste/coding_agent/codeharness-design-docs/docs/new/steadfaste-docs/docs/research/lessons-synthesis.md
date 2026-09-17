# Lessons Learned from Top Harnesses → Design Rules for Steadfaste

> Researched the mistakes of Claude Code, OpenAI Codex, OpenManus, OpenHands,
> OpenCode, Aider, and the cross-industry harness-failure literature. The goal:
> learn from THEIR mistakes so steadfaste starts wise, not naive. Source
> detail in `docs/research/` (4 reports). This is the synthesis: every lesson →
> one concrete design rule.

## The meta-lesson (they all agree)

> **The model is almost never the problem — the harness is.** Gartner: >40% of
> agentic projects cancelled for *operational* reasons. Forrester: it's "not raw
> agent capability." MIT: 95% of pilots deliver no ROI. Every harness that
> failed did so because it **lost its dependable core to features** — and every
> one of them validates our thesis: **governance (risk/cost) is the product.**

## Design rules for steadfaste (mistake → rule)

### 1. Keep a minimal frozen core; everything else is a plugin/config
- **Mistake (everyone):** the "features!" temptation bloats past the dependable
  core, so integrators can't depend on any harness.
- **Rule:** the core is *only* — agent loop, durable state/resume, deterministic
  verification, failure taxonomy, governance/logging, cost visibility. Models,
  tools, linters, evals, integrations = config/plugins. Others plug INTO
  steadfaste, or configure it for a model (e.g. Claude). **Anti-bloat is a
  guardrail, not a preference.**

### 2. Verify at the harness gate, never trust the model's "done"
- **Mistake (Claude, Codex):** agents optimize for "finishing," so undefined
  success ships confident wrong answers.
- **Rule:** define "done" as a **checkable criterion** with real tool output
  evidence; a deterministic **maker/checker split** (one actor writes, a
  verifier proves) at the harness gate.

### 3. Durable, checkpointed state — resume is not restart
- **Mistake (rebuild era):** v1.0 skipped the deterministic spine; a late-late
  failure reruns everything (the "token tax").
- **Rule:** the Boss checkpoints + resumes from the interruption (exactly-once,
  intent journal). A failure mid-task costs only the tail, never the whole run.

### 4. State ≠ memory; enforce governance at runtime, never at the prompt
- **Mistake (Claude):** the "power user as safety system" assumption fails for
  median engineers; config-is-the-policy doesn't control a tool-invoking system.
- **Rule:** governance is runtime-enforced in the harness (approval gates,
  scoped audited permissions, deny-lists) — never a "please don't" in
  natural-language instructions. **The model can rewrite a rules file; it cannot
  rewrite a harness gate.**

### 5. Context is a budgeted resource — a giant instruction file crowds out the task
- **Mistake (Codex 1M-line AGENTS.md; Claude giant CLAUDE.md):** "context is a
  scarce resource... anything an agent can't access in context at runtime
  doesn't exist." Bloat costs 10x AND worsens output (lost-in-the-middle).
- **Rule:** give the agent a **map, not a manual** (~100-line navigation entry +
  progressive disclosure); path-scoped rules loaded on demand; hard size
  ceilings enforced in CI. **Our self-learning/template system must be
  retrieval-based, not accretive** — store lessons per-topic, fetch on demand;
  never append into a growing always-loaded file.

### 6. Cost is a harness responsibility, not a hope
- **Mistake (Claude's silent 10-20x cache-coast bug):** no cost telemetry →
  runaway spend unseen.
- **Rule:** the Boss meters cost + cache-hit per run, budgets per request (the
  Governor's cost policy), surfaces cost in every report. Model-agnostic core
  avoids the "one model co-evolves" mismatch trap.

### 7. Catch the "mission-critical" silent failures mechanically
- **Mistake (Codex):** CVE-2025-59532 (sandbox root from model `cwd`), and
  66.5% attack success / 0% framework defense / agents rewriting their own
  governance file in IssueTrojanBench.
- **Rule:** security boundaries are **below the model layer** (deny-lists,
  hooks, approval gates) and mechanically enforced — never a natural-language
  rule the agent can override or rewrite.

### 8. One config system, frozen schema, loud versioned migrations
- **Mistake (OpenHands `config.toml` + `settings.json`; OpenCode silent
  auto-migration):** parallel/silent config = confusion + drift.
- **Rule:** one `harness.jsonc` + JSON schema; unknown key = startup error;
  migrations are loud, versioned, and break loudly on mismatch — never silent.

### 9. Self-hosted = one command, not a knob farm; no magic repo layout
- **Mistake (OpenHands' sandbox/volume tangle = standing "connection refused"
  class; `.openhands/setup.sh` `hooks.json` silently not firing after a layout
  change; Aider hard-depending on git):**
- **Rule:** one-command install/update/uninstall (the Homebrew lifecycle); the
  execution/runtime backend is a plug-in point, never folded into the core; never
  activate behavior from magic folder layout; test the real deployed path.

### 10. Dependable = a stable contract others can build on
- **Mistake (OpenManus' "unstable" entry points + demo-grade prototype churn):**
  release churn is a tax on every integrator/consultant.
- **Rule:** source compatibility is a hard promise; the ABI + core contract is
  frozen and additive-only so devs/integrations/consultants can depend on
  steadfaste the way they can't depend on today's churning harnesses.

## What this VALIDATES about our design

| Our thesis | The evidence |
|-----------|--------------|
| Governance (risk/cost) is the product | Claude's "enterprises need the layer underneath"; the governance failures in Codex's security and Claude's cost bugs |
| Minimal frozen core + plugins/config | anti-bloat is the consensus metic; Microsoft + LangChain both *shrank* their way to reliability (Azure 100+ bespoke tools → filesystem primitives, 45%→75%; Nemotron within 1pt of Opus at 1/10 cost on harness-tuning alone) |
| Self-healing / learning | "resume, don't rerun" is the rebuild-era demand; retrieval-based lessons avoid instruction bloat |
| Runtime governance, not prompt | IssueTrojanBench: model can rewrite its rules file; it cannot rewrite a gate |
| Dependable for integrators | every churn warning is an argument for a frozen core |

## Bottom line

The top harnesses failed (or struggle) not on model capability but on **harness
discipline: bloat, no runtime governance, no durable resume, no verification
gate, silent cost, config drift.** Steadfaste's response is a **small, frozen,
well-governed core** — the thing the market is asking for and nobody currently
ships dependably. Learn from their mistakes: keep the core small, enforce below
the model, verify at the gate, resume from checkpoints, and let everything else
plug in.