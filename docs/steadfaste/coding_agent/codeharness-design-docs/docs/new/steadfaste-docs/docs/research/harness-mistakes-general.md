# Harness Mistakes & Failure Modes — Cross-Industry Research

**Project:** steadfaste · **Date:** 2026-09-11
**Scope:** General coding-agent harness failure modes — what broke, who broke it, and the concrete design rule for a new harness to avoid repeating it.
**Governing doctrine (owner):** *The core must stay small.* Anti-bloat is a first-class requirement. "Losing the core to features" is precisely why developers, integrators, and consultants cannot depend on any harness today. Outside parties must be able to build on steadfaste with confidence — which means the core is a stable, minimal, frozen contract, and everything else plugs in or configures it. The design rule that recurs below is: **keep a minimal frozen core + let everything else be a plugin/config.**

---

## 0. Framing: the harness, not the model

The single most consistent finding across every source: **when agents fail, the model is rarely the thing that broke.** Gartner predicts >40% of agentic AI projects will be cancelled by end of 2027 for *operational* reasons (escalating cost, unclear business value, inadequate risk controls) — not model weakness. Forrester is blunter: the constraint on scaling agents is "orchestration, governance infrastructure, and risk management, not raw agent capability." MIT's GenAI Divide report attributes the ~95% of enterprise pilots that delivered no measurable return to a "learning gap" — generic tools that "don't learn from or adapt to workflows" — not to model quality.

The harness is the chassis, cooling, and steering; the model is the engine. A better engine does not write your definition of "done," grant access to a system, or keep evals honest. This report is about the chassis.

---

## 1. The Verification Bottleneck Paradox (speed vs. reliability)

### The mistake
Code **generation** became essentially free, so the bottleneck moved downstream to **verification** — but verification stayed manual. The result is a paradox: agents made writing faster while *net developer toil stayed flat or grew*, because humans now spend their time reviewing unreliable output instead of writing it.

### Who made it / where it shows up
- **Sonar (State of Code 2026):** 42% of all code is now AI-generated, yet **96% of developers do not fully trust** that AI-generated code is functionally correct. Only **2.6% of experienced developers "highly trust"** AI output; 20% "highly distrust" it.
- **byteiota (2026):** documents the deeper paradox — **96% distrust, but ~48% don't verify.** Distrust does not translate into checking. Confident hallucinations and "plausible but subtly wrong" output are *non-obvious by design*, so the human reviewer is a poor safety net.
- **The New Stack / Sonar:** "AI promised to eliminate developer toil but created a new one — while code generation is faster, developers now spend more time reviewing unreliable AI code."
- **Anthropic (April 23 postmortem):** a real-world case where verification confidence collapsed because of *harness-level* changes (a default reasoning-effort downgrade, a caching-optimization bug that dropped thinking history from stale sessions, an overly aggressive verbosity-limiting prompt) — none of them model changes.

### Design rule for steadfaste
**Move verification into the harness as a deterministic, always-on gate — never leave it to the human or to the generator.** The maker/checker split (a different model verifies than the one that generated) plus computational controls (linters, type checks, tests, `diff` inspection, replay of real commands) are the reliable layer. The generator and the verifier must be separate stages in the core loop. "It ran" must be evidenced by the harness capturing real tool output, not by the model asserting success.

**Anti-bloat corollary:** verification is a *core* responsibility (the contract that "this thing actually works" is what outside builders depend on), but the *specific* verifiers — the linter, the test runner, the language toolchain, the eval harness — are plugins/config, not baked into the core. The core guarantees *that* verification runs; the plugins decide *what* "correct" means for a given stack.

---

## 2. Why Agents Fail in Production (governance, orchestration, reliability)

### The mistake
Production failures are **operational and structural**, not capability failures. Three recurring root causes, and seven recurring deployment patterns.

**Beam.ai / Forrester — three root causes (none is the model):**
1. **The agent never knew what "done" meant.** Specs describe the *task*, not the *outcome*. With no checkable success criterion, the agent optimizes for "finishing," produces output that *looks* complete and passes a casual glance — and ships wrong. A more capable model produces *more confident wrong answers* when the target is undefined.
2. **The agent couldn't reach what it needed.** It is asked to do a job requiring a system/record/tool it cannot reach, so it improvises, hallucinates the missing input, or stalls. "An agent that cannot see the ERP record will not reason its way to the right number. It will invent one."
3. **Evaluations stopped describing reality.** Evals pass while real performance drifts; dashboards stay green while customers see errors. A 2026 production analysis found a **~37% gap between lab benchmark scores and real-world deployment performance**. LLM-as-judge scores are only useful when they correlate with human judgment — without a human-labeled reference set, "teams optimize for metrics that don't reflect actual quality."

**Digital Applied — the "88% problem," seven patterns:**
scope creep · data-quality failures · security blockers · integration complexity · **cost overruns** · **governance gaps** · organizational resistance. Key structural insight: errors **compound** across multi-step agents (a 95%-accurate agent loses its reliability guarantee by step ten).

**NIST / Forrester governance gap:** >half of enterprises report governance gaps even after adopting NIST AI RMF, "because a policy document can't control an autonomous, tool-invoking system." The agent's *reach* — what it can read/write/call — is the real surface, not the policy text.

### Design rule for steadfaste
**Encode "done" as a checkable, machine-evaluable success criterion at the harness level — not in prose.** Every task carries an explicit definition of correct that the harness can grade against (exit code, test pass, value match, invariant hold). Tool reach must be **scoped, audited, and explicit**: the harness declares what an agent may read/write/call and logs every action, because reach — not policy — is the true governance surface. Evals must run **against live traffic with a maintained human-labeled reference set**, feeding production outcomes back in.

**Anti-bloat corollary:** governance and observability belong in the core as a *thin, stable contract* (what actions are permitted, what's logged, what "done" means). The *specific* integrations (ERP, CRM, system-of-record, specific guardrail policies) are plugins. The failure mode to avoid is the enterprise harness that grows bespoke integrations and per-client governance logic *into its own core* until the core is an unreviewable pile — which is exactly why integrators and consultants stop trusting it.

---

## 3. The Failure-Classification Taxonomy (context / constraint / verification / planning)

### The mistake
Teams treat "the agent failed" as one undifferentiated problem and reach for one undifferentiated fix (usually "a better model"). In reality failures cluster into a small number of distinct classes, each demanding a different harness component — and the failure *mix* varies dramatically by environment.

### Who made it / where it shows up
- **deepset (May 2026, "Harness Engineering: ...by engineering the system, not the model"):** the canonical four-way failure classification — **context, constraint, verification, planning** failures — each mapped to a specific harness component. Their concrete result: **harness-only changes moved agents 20+ ranking positions without swapping the model.** This is the evidence that the classification is actionable, not academic.
- **Cobus Greyling (Medium) — Four-Layer Agent Failure Taxonomy:** action realisation / tool-call formatting failures are a distinct layer; the failure *mix* varies per environment (in Telecom, ~90% of failures concentrate in contract and action-realisation problems).
- **Anthropic "Demystifying Evals for AI Agents":** unit-test-style evals fail for agents — you must measure by failure class, not by function.

### Design rule for steadfaste
**Classify failures, don't just count them.** The harness should tag every failure with its class (context / constraint / verification / planning) and route each class to its own fix: context failures → context delivery/compaction; constraint failures → tool reach and permissions; verification failures → the deterministic gate; planning failures → planning artifacts and task decomposition. A harness that can name *why* it failed is the difference between a repair loop and a blind retry loop.

**Anti-bloat corollary:** the taxonomy is a *core* abstraction — four named categories, stable, frozen. The *remediation logic* per category (what a context failure should do in *this* stack, which linter a verification failure should call) is config. Don't let remediation logic for every conceivable environment creep into the core; let it be supplied by plugins.

---

## 4. The Rebuild Era — recovery/resume, durable orchestration, cost

### The mistake
The first wave deployed agents fast without "the plumbing" — no durable state, no resume, no recovery. Long-running workflows crash, and the only option is to **rerun the entire flow from step one**, multiplying inference cost ("the token tax") and latency. Teams then rebuild "version 2.0 of the same agent" on a durable foundation — having already paid twice.

### Who made it / where it shows up
- **Temporal Technologies (Preeti Somal, SVP Engineering):** "We do have a lot of customers that come to us where they're building version 2.0 of the same agent. They had to move really fast, but they didn't take care of the plumbing. Things crash and burn, and then they're back to rebuilding with the reliable foundation." The answer she frames: a **deterministic spine** — deterministic orchestration wrapping the probabilistic model, which retries a failed model call, and on a later failure **"picks up from where that failure happened."**
- **State vs. memory distinction (Somal):** *state* = where the agent is in the process, which actions completed, where to resume after failure; *memory/context* = information carried forward. Conflating the two is a core reliability bug — you cannot resume from memory alone.
- **Cost economics:** "What you care most about is making sure that you can recover and that you're not paying the token tax if something goes wrong." Resume-from-interruption, not restart-from-scratch, is what keeps cost and latency sane.
- **The "lift-and-shift" analogy (Somal):** the rush to deploy agents before modernizing the underlying architecture mirrors the cloud lift-and-shift wave — "everybody realized you're spending more money on cloud and we haven't gotten value there."
- **Meta's Ranking Engineer Agent (REA):** a production case study — hibernate-and-wake checkpointing to resume interrupted 6-hour ML tasks without losing context across days.
- **Durable orchestration platforms (Temporal, Restate, DBOS):** all built on the same premise — agents need durable execution, fault tolerance, and step-level resume.

### Design rule for steadfaste
**Build a durable, resumable execution core from day one — never bolt recovery on later.** Every task step is checkpointed as durable state (distinct from context/memory), so a crash resumes from the point of failure rather than restarting. The orchestration layer is *deterministic*; the model is *probabilistic*; the spine is what makes the whole system dependable. Observability into where tokens are spent (step-by-step, "a single pane of glass") is a first-class cost-control feature, not an afterthought.

**Anti-bloat corollary — this is the doctrine's strongest case.** The version-1.0 agents that "crashed and burned" did so because their orchestration/state/recovery logic was *bespoke, bolted-on, and unreviewable* — bloat that grew faster than the dependable core. The rebuild-era lesson is *not* "add more features to the harness"; it is "the dependable core is exactly the small set of guarantees — durable state, resume, deterministic orchestration, cost visibility — that everything else can rely on." If that minimal core is stable, integrators can build on it; if it bloats, they cannot. **Recovery/resume, state, and cost-visibility are core. The specific workflows, tools, and models are not.**

---

## 5. Model-Mismatch & Context-Bloat Cost Failures

### The mistake
Two cost/quality failure modes, both harness-level:

**(a) Context bloat.** Context accumulates — tool outputs, retrieved docs, multi-turn reasoning — and fills the window. Sending a large context on *every* call multiplies API cost directly. Beyond cost, quality *degrades*: "You upgraded to a model with a 128K context window. Your costs went up 10x. Your responses got worse. The agent now ignores instructions buried in the middle of a 50K token context" (lost-in-the-middle). LangChain names the long-horizon variant **"context rot"** — stale, contradictory, or redundant context that degrades output over a long task.

**(b) Model mismatch.** Using the wrong model for the job — a frontier model for a trivial step (cost overrun) or a small model for a hard step (silent failure) — with no routing. LangChain's "tuning the harness, not the model" playbook shows the flip side: **harness-only tuning brought Nemotron 3 Ultra within one point of Opus 4.8 on Deep Agents at roughly one-tenth the cost ($4.48 vs $43.48).** The lesson is *fit* — how much quality actually reaches the task — not raw model capability. Anthropic's April 23 postmortem adds a third mode: a **caching-optimization bug** that silently dropped thinking history from stale sessions, and a verbosity-limiting prompt — harness adjustments that degraded output while saving pennies.

### Who made it / where it shows up
- Context bloat: a documented, cross-vendor failure (AppXlab "context engineering" patterns; betterclaw "agent losing context" guide; the towardsai piece on 128K windows that cost 10x and got worse).
- Model mismatch: NotDiamond's "interactive benchmarks for model routing" — routing exists precisely to "maintain frontier quality while reducing cost"; LangChain Nemotron playbook; the "smart models produce dumb agents" critique (Saurabh Singh) that the hard problem is orchestration/reliability/memory/observability/governance/verification, not model IQ.

### Design rule for steadfaste
**Make context a budgeted, engineered resource and make the model a configuration knob, not a harness assumption.** The core must: (1) compact/select context aggressively before each call (Write/Select/Compress), never resend the whole window; (2) route each step to an appropriate model by *task fit*, with cost as a first-class signal; (3) surface token spend per step. The model is *config* — a specific model (e.g. Claude) is a configuration of the harness, never a hard dependency baked into it.

**Anti-bloat corollary — the co-evolution trap.** The awesome-harness-engineering list flags a warning explicitly relevant here: models trained *with* a specific harness become overfitted to that design, so "harness architecture choices have lasting consequences." Anthropic's own guidance is "remove harness assumptions as capabilities improve" and "build on tools Claude already knows." Translated to doctrine: **a harness that bakes any single model's behavior or a single vendor's scaffolding into its core has already lost its dependability** — it breaks the moment the model changes. The core must be model-agnostic; the model is a plugin/config. This is the same rule as everywhere else: *small frozen core, everything else plugs in.*

---

## 6. Cross-Cutting Lessons (top 8)

1. **The model is almost never the problem — the harness is.** Every source converges here (Gartner 40% cancellation for operational reasons; Forrester "not raw agent capability"; MIT 95% no-ROI "learning gap"). Design the system around the model, not the model around the system.

2. **Keep a minimal frozen core; everything else is a plugin/config (owner doctrine).** The dependable core is the small set of guarantees outside parties rely on — the agent loop, durable state/resume, deterministic verification, the failure taxonomy, governance/logging, cost visibility. Every model, tool, linter, eval, and integration is config. **The reason developers/integrators/consultants cannot depend on harnesses today is that they "lost the core to features" — bloat made them unstable, unreviewable, and un-buildable-on.** Anti-bloat is not a style preference; it is the dependability contract.

3. **Verification is a harness gate, not a human chore.** Generation is free; verification is the bottleneck. 96% distrust, ~48% don't check. Ship a deterministic maker/checker split with the checker as a *different* stage/model, evidenced by real tool output — never trust the generator's self-report.

4. **Define "done" as a checkable criterion, not prose.** Agents optimize for "finishing"; with no machine-evaluable success criterion they ship confident wrong answers. Encode the definition of correct at the harness level.

5. **State ≠ memory; resume ≠ restart.** Durable checkpointed state (which step, which actions, where to resume) is distinct from context. Without it, a crash forces a full rerun and pays "the token tax." Build the deterministic spine first — the rebuild era exists because v1.0 skipped it.

6. **Reach is the real governance surface.** A policy document cannot control an autonomous, tool-invoking system. Governance = scoped, audited read/write/call permissions + logging, enforced by the harness, not a compliance PDF.

7. **Context is a budgeted resource, and the model is a knob.** Bloat costs 10x and *worsens* output (lost-in-the-middle, context rot). Compact before every call; route by task fit; keep the model configurable so no single model or vendor becomes a core assumption (the co-evolution/overfitting trap).

8. **Classify failures, route to fixes; keep evals honest against live traffic.** Four classes — context / constraint / verification / planning — each with its own remediation. Lab-vs-production is a ~37% gap; frozen eval sets drift and lie. Continuous evaluation against real traffic with a human-labeled reference set is the only honest dashboard.

---

## Sources

- **awesome-harness-engineering** (github.com/ai-boost) — the field's central index; Birgitta Böckeler's harness-engineering mental model; the co-evolution/overfitting warning; deepset's four-way failure classification; Anthropic/OpenAI/LangChain/Meta/Red Hat foundations.
- **deepset — "Harness Engineering: ...engineering the system, not the model"** (May 2026): context/constraint/verification/planning taxonomy; 20+ ranking-position gain via harness-only changes.
- **Beam.ai — "Why AI Agents Fail in Production: 3 Root Causes That Aren't the Model"** (Fredrik Falk): unclear success criteria, insufficient tool/data access, evaluation drift; Gartner 40%, Forrester, MIT 95% figures.
- **VentureBeat via Temporal / Tech Next Portal — "AI agents are entering their rebuild era..."** (May 30, 2026, Preeti Somal): deterministic spine, state-vs-memory, token tax, lift-and-shift analogy.
- **AI Agent Corps — "Agentic AI Scaling Challenges"** (Digital Applied 88% failure rate, seven patterns).
- **Sonar / The New Stack / byteiota — "The AI Verification Bottleneck"**: 42% AI-generated, 96% distrust, 2.6% high-trust, 48% don't check.
- **Anthropic — April 23 postmortem; "Demystifying Evals"; "Building Effective Agents"; "Harness Design for Long-Running Application Development."**
- **LangChain — "The Anatomy of an Agent Harness"; "Tuning the harness, not the model"** (Nemotron 3 Ultra vs Opus 4.8, $4.48 vs $43.48).
- **Cobus Greyling — "The Four-Layer Agent Failure Taxonomy."**
- **Microsoft — Azure SRE Agent context-engineering posts** (100+ bespoke tools → filesystem primitives; "Intent Met" 45% → 75%) — a concrete case of *reducing* harness surface improving reliability.
