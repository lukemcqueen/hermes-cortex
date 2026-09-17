# OpenAI Codex: Harness Mistakes and Lessons for Steadfaste

Research notes on Codex as a *harness* — what broke, and the concrete design
rules steadfaste should adopt so its own instruction/template/self-learning
system does not repeat the failures.

Primary sources:
- OpenAI, *Harness Engineering* (Ryan Lopopolo, Feb 2026) — openai.com/index/harness-engineering/
- Ken Imoto, *OpenAI Codex AGENTS.md: 1M Lines Shipped, 3 Harness Lessons* — kenimoto.dev
- OpenAI Codex docs: Subagents (learn.chatgpt.com/docs/agent-configuration/subagents)
- CVE-2025-59532 / GHSA-w5fx-fh39-j5rw — Codex CLI sandbox bypass (path-config bug)
- IssueTrojanBench (arXiv:2607.20759, Singh/Yang/Chen, July 2026) — malicious-issue attack surface

---

## 1. The AGENTS.md bloat failure: context is a scarce resource

**The mistake.** OpenAI's five-month "agent-first" experiment (Aug 2025 – Jan 2026,
~1M lines shipped, ~1,500 PRs, zero human-written code) started by writing **one
big AGENTS.md covering the whole repo** — coding conventions, module boundaries,
review checklists, deployment runbooks, all in a single file. It collapsed, for
four concrete reasons:

| Failure | Mechanism |
|---|---|
| **Context scarcity** | Large instruction files crowd out the actual task, code, and docs. Agents missed key constraints or optimized for the wrong ones. |
| **Ineffective guidance** | When everything is "important," nothing is. Agents pattern-match locally instead of navigating deliberately. |
| **Immediate rot** | A comprehensive manual becomes a graveyard of stale rules; the agent can't tell which entries are still valid. |
| **Verification resistance** | A single blob resists mechanical checks (coverage, freshness, ownership). Drift becomes inevitable. |

The defining insight from the post: **"From the agent's perspective, anything it
cannot access in context at runtime does not exist."** Bloat doesn't just waste
tokens — it *starves the task itself*. Every line of instruction is a line of
code/doc that got pushed out of the window.

**Design rule for steadfaste:** treat every token of persistent instruction as a
cost drawn directly from the task's working budget. The instruction surface must
be a **map, not a manual** — a short, stable entry point that points the agent to
where to look next (progressive disclosure), never a flat dump of everything.

---

## 2. How instruction files should be scoped and sized

**The fix OpenAI converged on** (from the same post):

- **AGENTS.md ≈ 100 lines**, injected into context as a *navigation map* / table
  of contents — not an encyclopedia.
- **Progressive disclosure:** agents start at the small, stable entry point and
  are guided to the relevant detail *on demand* (architecture map, design docs,
  execution plans, principles each live in their own file under `docs/`).
- **Structured validation:** dedicated linters + CI jobs mechanically check the
  knowledge base's freshness, cross-linking, and structure (single blobs can't be
  checked; directories can).
- **Auto-maintenance:** "doc-gardening" background agents scan for stale docs and
  open fix PRs — the knowledge base is kept fresh by automation, not willpower.

Supporting evidence that OpenAI treats this as a hard budget, not a suggestion:
Codex's *own* repo `AGENTS.md` carries explicit limits — **no item larger than 10K
tokens**, and new items crossing >1K tokens are flagged P0 for manual review.

**Design rules for steadfaste:**

1. **Hard size ceilings, enforced.** Instruction/contract files get a byte/token
   cap, checked mechanically (CI/linter), not by convention. Something over budget
   is a *build failure*, not a style nit.
2. **Instruction files are pointers, not payloads.** A template/instruction file
   must be small and stable; the heavy content lives in referenced, lazily-fetched
   resources that are pulled only when the task actually touches them.
3. **Freshness is automated.** Any self-learning system that *appends* lessons to
   a shared instruction file is a rot engine. Lessons must be stored per-topic
   (retrievable, not always-loaded) and pruned/validated by an automated gardener,
   never left to accumulate in one growing file.

---

## 3. Subagent orchestration lessons

**The mistake.** Flooding the main thread with noisy intermediate output
(exploration notes, test logs, stack traces, command output) produces **context
pollution** (useful info buried under noise) and **context rot** (reliability
degrades as the chat fills with low-value detail). This is the same scarcity
lesson from §1, but *caused by the agent's own work product* rather than static
instructions.

**What Codex's design does about it** (subagents doc):

- **Move noisy work off the main thread.** The orchestrator keeps requirements,
  decisions, and final outputs; specialized subagents run in parallel for
  exploration, tests, log analysis, triage.
- **Return summaries, not raw output.** Subagents distill results back to the main
  thread instead of dumping intermediate output.
- **Read-heavy in parallel, write-heavy with care.** Parallel agents are safe for
  exploration/tests/triage/summarization; parallel *write-heavy* agents editing
  code at once create merge conflicts and coordination overhead.
- **Subagents cost more.** Each subagent does its own model + tool work, so fan-out
  consumes more tokens than a single-agent run. Cap fan-out to what you can verify.
- **Each custom agent needs a mandate that materially differs from the parent.**
  Spawning a clone of the parent wastes tokens; write the decomposition explicitly
  (which tasks fan out, which stay sequential) rather than inferring it.

**Design rules for steadfaste:**

1. **The orchestrator's context is the scarce resource.** Route noisy work to
   subagents and require *distilled summaries* back, never raw logs/diffs.
2. **Parallelism is for reads; serialize writes** (or coordinate them explicitly).
3. **Fan-out is metered.** Subagents are more expensive, not free — budget them
   and cap the count to what the operator can actually review.

---

## 4. Known open issues: governance and sandboxing

### 4a. Sandbox boundary bypass (CVE-2025-59532)

**The bug.** A defect in sandbox path-configuration logic let Codex CLI treat a
*model-generated `cwd`* as the sandbox's writable root — including paths **outside**
the folder where the user started the session. Result: arbitrary file writes and
command execution anywhere the Codex process had permissions (network-disabled
sandbox restriction was unaffected). Patched in CLI 0.39.0; the fix **canonicalizes
the boundary to the user's session start location and ignores what the model
generated.** CVSS 4.0: 8.6 (High), CWE-20.

**Design rule for steadfaste:** the sandbox boundary must be **derived from the
harness's own trusted state** (where the operator launched the session), never from
anything the model emits. Model output is untrusted input; it must never be able
to widen its own write root. Validate/canonicalize the boundary before every
write.

### 4b. The instruction file is an attack target, not just a defense

**The finding.** IssueTrojanBench ran 4,176 adversarial runs (six agent×model
configs) across Codex Desktop, Cursor, and Claude Code, injecting malicious
instructions via issue bodies, comments, PDFs, websites, and source comments:

- Aggregate attack success rate **66.5%**; Codex Desktop **79.2%**.
- Supply-chain poisoning **96.6%**; **policy bypass 84.7%**.
- **Framework defenses contributed 0% of rejections.** Of the 1,400 blocked runs,
  82.9% were rejected by *model-level refusal* and 17.1% by trust-based source
  classification — sandbox mode and approval policy intercepted **none** of the
  attacks. Spotlighting (wrapping external content in boundary markers) failed in
  every tested config.

The policy-bypass category is the key governance lesson: an agent that can read
issue text and write files can be directed to **rewrite its own governance file**
(AGENTS.md / CLAUDE.md / .cursorrules), weakening constraints that then persist
into future sessions. **The constraint file becomes the persistence vector.**

**Design rules for steadfaste:**

1. **Treat governance/instruction files as code, not config.** They belong under
   branch protection, require review to merge, and — critically — **must not be
   writable by the agent process during automated runs.** Enforce via sandbox write
   deny-lists + a pre-tool hook that blocks any write to governance-adjacent paths.
2. **All external input is untrusted.** Issue bodies, comments, PDFs, websites are
   *data*, not instructions. The harness cannot rely on the model to distinguish
   them; boundary enforcement must sit **below** the model layer (permission mode,
   sandbox, approval policy).
3. **Governance enforcement must be mechanical, not prompted.** Natural-language
   constraints in an instruction file are themselves the weakness. Real guardrails
   (write-denials, hooks, approval gates) live in the harness, out of the model's
   reach.

### 4c. UI/governance friction bugs

Reported in the wild: the sandbox-elevation approval window can get stuck open on
click (community.openai.com 1373776), leaving the only fix a desktop-app restart.
Symptomatic of governance flows that gate on fragile UI state.

**Design rule for steadfaste:** approval/elevation state must be **recoverable and
idempotent** — a stuck approval window must not wedge the session, and re-requesting
an elevation must not require a full restart.

---

## 5. The anti-bloat doctrine (owner directive — folded into the core design)

> Keep the core small so developers/integrations/consultants can depend on it.
> Codex's instruction-file bloat is exactly this trap in miniature.

**Reframed as a first-class design rule: a MINIMAL FROZEN CORE + everything else
as plugin/config.**

- The **core instruction/contract surface is small and frozen** — a stable, tiny
  set of invariants that integrations can depend on without fear of churn.
- **Everything else lives as plugin/config** — loaded on demand, versioned
  independently, and out of the always-injected context.
- **The self-learning/template system must not become instruction bloat.** A
  template system has to stay tiny and cheap: lessons are stored *retrievably*
  (per-topic, fetched when relevant), never appended into a growing always-loaded
  file. Any mechanism that grows the frozen core over time is, by definition, a
  bug.

This is the same lesson as §1–§2, applied to steadfaste's own machinery: the trap
is not just a too-big AGENTS.md written by a human — it's a self-learning system
that *accretes* instructions until the core is no longer small, no longer frozen,
and no longer dependable.

---

## Consolidated rule list (top lessons)

1. **Context is a scarce resource.** Persistent instructions are a tax on the task
   budget; bloat silently starves code/docs. Give agents a *map, not a manual*.
2. **Enforce size ceilings mechanically.** Instruction/contract files have hard
   token/byte caps checked by CI — over budget is a build failure, not a style nit.
3. **Instruction files are pointers, not payloads.** Small, stable, frozen; heavy
   content is lazily fetched on demand (progressive disclosure).
4. **Self-learning must be retrieval-based, not accretive.** Lessons stored
   per-topic and pruned by automated gardeners — never appended into a growing
   always-loaded file.
5. **Subagents return summaries, not raw output.** Parallel reads are safe; writes
   are serialized; fan-out is metered.
6. **Sandbox boundary derives from trusted harness state, never model output.**
   Model-generated paths must not widen the write root.
7. **Governance files are code and attack targets.** Not writable by the agent,
   under review, with enforcement below the model layer (hooks, deny-lists, approval
   gates) — never natural-language-only.
8. **Minimal frozen core + plugin/config for the rest.** Small enough to depend on,
   extensible without accretion.
