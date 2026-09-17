# Mistakes of Claude Code — a post-mortem for steadfaste

**Purpose:** Extract concrete "don't repeat this" lessons for a new coding harness (steadfaste). Four failure clusters are examined: (1) tracked critical bugs, (2) the "thin harness" governance gap, (3) Anthropic's performance-decline missteps, and (4) context/instruction bloat. Each closes with a design rule that validates steadfaste's core thesis — **governance is the product, not a bolt-on**.

**Sources:** [cc.bruniaux.com Known Issues](https://cc.bruniaux.com/guide/known-issues/) (tracked critical bugs, last updated Apr 2026), [Ona — "The enterprise agent problem Claude Code wasn't built to solve"](https://ona.com/stories/enterprise-agent-problem) (Mar 2026), [Fortune — "Anthropic faces user backlash over performance decline"](https://fortune.com/2026/04/14/anthropic-claude-performance-decline-user-complaints-backlash-lack-of-transparency-accusations-compute-crunch/) (Apr 2026), plus community reports on context bloat.

---

## 1. Known critical bugs — silent failures the harness does not surface

**The mistake.** Three classes of verified critical bugs shipped to production and sat unpatched for months:

- **Prompt-cache corruption (CC#40524, Mar 2026–present).** Three independent bugs break Anthropic's prefix-based prompt caching, turning discounted `cache_read` into full-price `cache_creation`. On `--resume`, a session JSONL writer strips `deferred_tools_delta` records, so the restored conversation re-announces all tools from scratch and every message position shifts — the cache prefix collapses. Sessions measured at **4.3–34.6% cache-read ratio** (vs 95–99% healthy), i.e. **10–20x cost per turn** in the worst sessions. Bugs 2 and 3 remain unpatched as of v2.1.88.
- **GitHub issue auto-creation in the wrong repo (#13797, Dec 2025–present).** Claude Code creates issues in the **public** `anthropics/claude-code` repo instead of the user's private repo — 17+ confirmed cases of exposed DB schemas, API credentials, and infrastructure architecture. No confirmation prompt before posting to a public target.
- **Excessive token consumption (#16856, Jan 2026–present).** 4x–20x token burn for identical operations; weekly limits exhausted in 1–2 days.

**The failure mode.** The harness is a *thin* wrapper (Boris Cherny's own words: "the thinnest possible wrapper over the model") that treats the model call as the product and the execution/cost/security layer as incidental. There is no instrumented control plane watching cache hit ratios, no destination-validation gate on destructive or externally-visible writes (issue creation), and no cost telemetry that would have caught a 20x regression within hours instead of months. The bug itself is a symptom; the real failure is **no observability layer that turns "the model did something" into "the organization can see and verify what happened."**

**Design rule for steadfaste.** *The harness must measure and gate the loop, not just drive the model.* Ship with first-class, always-on instrumentation of the two things that silently go wrong and hurt enterprises most: **cost (cache hit ratio, tokens/turn, cost/turn, per-org caps)** and **blast radius (a mandatory destination-confirmation gate on any externally-visible write — issue creation, PRs, posts — with a "where is this going?" prompt when the target is public/unknown)**. A bug that costs 10x silently is a governance failure, not a model failure; the harness should have raised the alarm.

---

## 2. The "thin harness" problem — capability is solved, governance isn't

**The mistake.** Claude Code optimizes for the individual power user, and explicitly *defines itself by* thinness. From the Ona piece: enterprises like the model but cannot adopt a harness whose safety system is assumed to be "the user." The four enterprise questions Claude Code doesn't answer:

1. How do you scale beyond a few power users without sprawl?
2. How do you keep security/governance happy without killing velocity?
3. How do you make execution reproducible deterministically across hundreds of repos?
4. How do you control cost at the team level?

**The failure mode.** A thin harness *assumes a power user as the safety system*: the operator steers, debugs, and self-governs. That assumption does not transfer to the median engineer, to background/fleet agents running unattended, or to a CISO who must say "yes" on a compliance checklist. Guardrails that live only in prompts can be routed around; permission rules that live only in a config file on one laptop don't reproduce across a fleet. The result is exactly the mirror failure: a very *capable* thin harness that enterprises *cannot govern*, so they stall at pilot stage or bolt on a third-party platform to supply the missing layer.

**Design rule for steadfaste.** *Don't standardize on the interface — standardize on the layer underneath.* steadfaste must ship **governance as the core product surface, not a plugin**: identity, least-privilege RBAC, **runtime-enforced** command/action deny-lists (not prompt-level suggestions), immutable audit logging of every execution, reproducible environments (known-good starting state), team-level cost caps, and org-level policy propagation. These are platform primitives — the reason a CISO says "yes" — and they must be present on day one, deterministic, and enforceable in code (a deny-list that blocks even if the agent tries to route around it), not contingent on an individual operator's expertise.

---

## 3. The performance-decline backlash — silent configuration changes and transparency failures

**The mistake.** Anthropic degraded perceived quality through **silent, undocumented harness changes** and then blamed users before acknowledging systemic issues:

- **Default effort dropped from "high" to "medium"** to economize on tokens — while the in-product indicator still *showed* "high," masking the regression for over a month. Users silently got medium-quality reasoning under a "high" label.
- **Thinking tokens cleared per turn after idle** — a code defect made the once-on-resume clear fire on *every subsequent turn*, causing progressive forgetfulness.
- **A verbosity-reduction system-prompt instruction** combined with other active prompt changes to drop coding quality.
- The broader context (Fortune): Anthropic reduced default effort to save compute, listed the change only in a changelog, and initially implied users were to blame. Fortune notes the brand risk precisely because Anthropic had *built its reputation on transparency*.

**The failure mode.** The company made a *quality-affecting configuration change* and neither (a) surfaced it to the user, nor (b) decoupled the visible control (the "/effort" indicator) from the actual behavior. Users cannot tell whether output degraded because of the model, the harness, or a config knob they never saw. The backlash became a *trust* crisis, not a capability crisis — cancellations, a 250+ comment HN thread, and a formal postmortem promising better eval and rollout practices.

**Design rule for steadfaste.** *Configuration changes that affect behavior must be visible, versioned, and reversible — and the UI must never lie about what is active.* Concretely: every quality-relevant knob (effort/reasoning level, model, verbosity, context policy) must be (1) shown as its *actual* resolved value at all times, (2) changelogged per-org so an admin can see "what changed on Tuesday," and (3) pinned, so a quality regression is attributable and reversible per team rather than a silent global toggle. **Governance is the product** means the harness tells the operator *what configuration is live and what changed*, instead of hiding a silent degradation behind a stale label.

---

## 4. Context / instruction bloat — too much guidance becomes non-guidance

**The mistake.** The dominant community answer to "make Claude Code follow my rules" is to grow a single `CLAUDE.md` into a giant instruction file — and to mount always-on MCP servers and skills — until the guidance *crowds out the task*. As captured in community writeups: *"Context is limited, so a giant instruction file crowds out the task, and relevant docs. Too much guidance becomes non-guidance — agents start pattern-matching locally instead of intentionally navigating the codebase."*

**The failure mode.** Instruction bloat produces two concrete failure modes:

1. **Cost/context exhaustion.** Every turn re-sends the full system prompt, memory files, tool schemas, and MCP context — a bloated `CLAUDE.md` and a wall of always-on servers consume tokens *before the user types anything*, which is exactly the substrate on which the "excessive token consumption" and "prompt too long / session irrecoverable" bugs from §1 flourish.
2. **Attention dilution.** When the instruction surface exceeds what the model can actually attend to, the model stops following the *intent* of the rules and starts pattern-matching locally against the nearest chunk — it "optimizes for the wrong things," misses key constraints, and the guidance becomes noise.

**Design rule for steadfaste.** *Instruction surface must be scoped, loaded on demand, and sized against attention — never a single ever-growing file.* Concretely: (1) **path/scope-scoped rules** — instructions bind to the files/workspace they actually govern, so the model only carries what applies; (2) **on-demand skill/tool loading** — MCP servers and skills are lazily loaded, not always-on, with a cost meter that makes "you are carrying 87K tokens of inactive guidance" visible; (3) **a hard budget on the always-present surface** — the harness enforces a ceiling on the persistent instruction+tool context and forces overflow into retrievable, on-demand store. Governance scales by *selective loading*, not by *accumulation*.

---

## 5. The anti-bloat boundary — where a harness tips from dependable core into unruly bloat (owner doctrine)

**The mirror lesson.** The "thin harness can't govern" failure has an equal-and-opposite trap: a harness that responds by *adding* governance, observability, and orchestration into the core until it becomes everything — and in doing so loses the one thing that made a thin harness dependable: a small, frozen, predictable core that a developer, an integration, or a consultant can rely on in isolation.

**The boundary ("when does a harness tip?").** A harness tips from *dependable core* into *unruly bloat* the moment a capability is shipped **inside the core** that (a) not every consumer needs, (b) changes frequently, or (c) carries its own opinionated configuration — because then the "dependable" core is dragged along by the churn and surface area of things that don't belong to it. Concretely, the tipping signals are:

- A new governance/cost/observability feature lands as a **hard dependency** of the run loop rather than an optional layer.
- The persistent instruction/tool surface (§4) grows because features are **on by default and resident in context** rather than loaded on demand.
- A "single harness" that must be *configured down* to be simple, instead of *configured up* to be powerful.

**Design rule for steadfaste.** *Minimal frozen core + everything else a plugin/config.* The core is small, stable, and dependable — the loop (read → plan → act → verify), the sandbox, and the governance *hooks/contract* — and it changes rarely. Everything else — model routing, observability dashboards, org policy, orchestration, specific-vendor integrations (e.g. configuring steadfaste *for* Claude specifically) — is a plugin or a config layer that others plug in, or configure on top, *without forking the core*. Governance lives in the core as a *stable contract* (a small set of enforced seams — audit log, deny-list, identity, cost cap), not as a sprawling feature set baked into the loop. This is how steadfaste avoids both failure directions at once: it is thin enough to stay dependable, and it ships governance as an enforced, minimal, frozen seam rather than an accreted mass.

---

## Top 6 lessons (summary)

1. **Governance is the product, not a bolt-on.** Capability is converging; the differentiator enterprises actually buy is the layer underneath — identity, runtime-enforced guardrails, audit, reproducibility, cost control. Build that into the core, day one.
2. **Instrument and gate the loop, don't just drive the model.** Ship always-on cost telemetry (cache-hit ratio, tokens/turn, org caps) and a mandatory destination-confirmation gate on externally-visible writes — the 10–20x silent-cost bug and the public-repo data leak are both governance failures the harness should have caught.
3. **Enforce at runtime, never at the prompt.** Prompt-level guardrails and a power-user-as-safety-system assumption do not scale to median engineers or background fleets. Deny-lists, RBAC, and audit must be code-enforced and least-privilege.
4. **Configuration changes must be visible, versioned, and reversible — and the UI must never lie.** The "high" label hiding a silent "medium" downgrade is what turned a config tweak into a trust crisis and mass cancellations.
5. **Scope the instruction surface, load on demand, and budget the always-present context.** A giant ever-growing `CLAUDE.md` crowds out the task and breeds both cost exhaustion and attention dilution; path-scoped rules, lazy tool loading, and a hard ceiling on resident guidance.
6. **Minimal frozen core, everything else a plugin/config.** Stay thin enough to stay dependable, and put governance in the core as a small *stable contract* — not as an accreted feature mass. The boundary is crossed when a not-universal, fast-changing, or opinionated capability becomes a hard dependency of the run loop.

---

*Report assembled by research subagent. Facts sourced from cc.bruniaux.com known-issues tracker, Ona's enterprise-agent essay, and Fortune's performance-decline reporting; verified against GitHub issue IDs (#40524, #13797, #16856) and official Anthropic postmortems where cited in sources.*
