# Steadfaste — Vision & Architecture

> The product thesis and the system shape, together. A raw model is a gamble;
> steadfaste is the harness that makes it a **dependable, self-improving
> producer**. This doc is the single place where the vision (why) and the
> architecture (how) meet. Read `docs/architecture/pm-summary.md` for the
> plain-english version; this is the design.

## 0. The one thing

> **"Do one thing well, better than everyone else."** Steadfaste's one thing is
> **the core + its interfaces** — the frozen contract at the center. We have
> thought of everything *around* it, so every other capability can be **built
> around that core**, not into it. That is why the core stays small, frozen, and
> dependable: it is the one thing we do better than anyone, and the reason
> developers / integrations / consultants can depend on it.

---

## 1. The thesis

**A raw model is a variable-gamble.** Left alone it will spend without limit,
touch anything, skip checks, and produce a different-quality result every run.

**Steadfaste is the harness that turns that gamble into a dependable producer:**
- it keeps the **quality high and essentially the same, run after run** (steadfast),
- it **costs less** (the right model, cheap-first escalation, real budgets),
- it **lowers risk** (that is what "enterprise" means: fewer surprises),
- and it **improves every interaction** (self-healing, self-learning → the next
  time is better).

The "agent" is therefore **not a thing — it is governance wrapped around a
brain.** The model is the raw decision-maker; the governance layer (risk/cost),
not the model, is what makes it safe, cheap, controlled, and auditable. That
layer is business-editable — rules and templates a non-coder changes — and *that*
is the product.

**The four-word version:** *the brain wrapped in risk/cost management.*
**The compounded promise:** *steadfast, and getting better every run.*

---

## 2. The system shape

```
      YOU  (a business user — Telegram, or the web screen)
            │  "fix the checkout bug, under $2"
            ▼
   ┌──────────────────────────────────────────────────────────┐
   │  1. THE GOVERNOR  ← the product (the governance layer)   │
   │  decides, for THIS request:                              │
   │  • budget + deadline           (cost)                    │
   │  • which model(s), cheap-first (cost)                    │
   │  • what it may/must-not touch  (risk)                    │
   │  • what needs human approval   (risk)                    │
   │  • which template/recipe       (repeatability)           │
   │  RULES + TEMPLATES — business-editable, no code.         │
   └──────────────────────┬───────────────────────────────────┘
                          │  a POLICY for this job
                          ▼
   ┌──────────────────────────────────────────────────────────┐
   │  2. THE BOSS  (the core — the enforcer)                  │
   │  • leases the job     • enforces budget/deadline         │
   │  • records every step • asks before risky (via policy)   │
   │  • retries / heals on failure                            │
   │  speaks the frozen Covenant → hands the policy to a worker    │
   └──────────────────────┬───────────────────────────────────┘
                          │  "run THIS, within THIS policy"
                          ▼
   ┌──────────────────────────────────────────────────────────┐
   │  3. THE BRAIN + TOOLS  (the worker — out-of-process)     │
   │  the model does the work: plan, read/edit code, run      │
   │  tests, call the model — always inside the policy,       │
   │  every step streamed back                                │
   └──────────────────────┬───────────────────────────────────┘
                          ▼
   ┌──────────────────────────────────────────────────────────┐
   │  4. THE RECORD  (Postgres default)                       │
   │  every task, policy, decision, approval, cost, outcome — │
   │  the durable, auditable memory                          │
   └──────────────────────────────────────────────────────────┘
        ▲
        │  THE LEARNING LOOP (feeds back into the Governor)
        └────────────────────────────────────────────────────┘
```

---

## 3. The four parts and their plain-English job

| # | Part | What it is | Plain-english job |
|---|------|-----------|-------------------|
| 1 | **Governor** | the governance rules + cost/method intelligence + templates | **The product.** Decides how to run this job safely + cheaply; editable by a business user. |
| 2 | **Boss** | the frozen core (enforcer) | The referee. Executes within the policy: budget, deadline, approvals, audit, retry. Never silently dies. |
| 3 | **Brain + Tools** | the model + its toolset (out-of-process worker) | The doer. Does the actual work, always inside the policy. Replaceable. |
| 4 | **Record** | the durable store (Postgres default) | The memory. Everything auditable; swappable DB. |

---

## 4. The three promises, and what powers each

1. **Dependable** — the Boss enforces: budget, deadline, exactly-once, retry.
2. **Visible** — the Record logs every decision/step/approval/cost; replayable.
3. **Governed** — the Governor alone decides; the brain only acts inside policy.

---

## 5. The self-healing / self-learning loop (the steadfaste multiplier)

This is what makes it *compounding*, not just consistent. It needs **two
engine pieces** beyond the four parts:

- **Lesson memory** (the "what worked" store): every run records its outcome —
  model used, cost, tools, whether it passed verification, how good the result
  was judged. This is a policy-aware memory of *what actually produced good
  results*.
- **Policy updater** (the "bake it in" step): reads the lesson memory and
  turns it into **better rules and templates** — promote the cheap-model-first
  recipe that keeps working, demote the one that failed, add a check that would
  have caught last run's bug. The update is **proposed to the Governor** (and its
  human owner), not silently applied — governance stays in charge.

So the loop is:

```
   run a job → record the outcome (cost, quality, failure) in lesson memory
   → policy updater turns the pattern into a better rule/template
   → the Governor uses it next time → the next run is better
```

That is "self-healing" (a failure becomes a check that prevents it) and
"self-learning" (a success becomes the recipe) — and it is the part that makes a
governed harness *both* steadfast and improving.

**Design guardrail:** the loop never bypasses the human. It proposes rule/template
changes and records everything; the human (or an explicit auto-approve policy the
human set) accepts. Governance stays in charge of the governance.

---

## 6. Standing decisions (locked)

- **Rust core** (the Boss: store, audit, bus, config, supervisor, gateway).
- **TypeScript modifiable layer** (the worker/brain-tools, the web UI, the
  swappable messaging/models/skills/context).
- **Postgres** default DB (swappable typed port).
- Ubuntu LTS enterprise base; cross-platform (unix/macos/windows); Homebrew
  lifecycle; the self-developing test/governance standard
  (`docs/standard/testing-governance.md`).
- **The Covenant (Covenant v1, JSON-over-stdio)** is the frozen seam; the Boss
  hands a worker a **policy** (not just a task) — this is a live design point
  to finalize before freeze.

---

## 7. What's still to nail (the honest open list)

- **Finalize the Covenant** (D1–D4 from the conversation): the `Task` shape now
  carries a **policy**; permission vocabulary; the wall-clock deadline; additive
  growth. *Do not freeze until settled.*
- **The Governor's rule/template language**: how a business user expresses a
  rule ("sales-team ≤ $0.50, cheap model first") without code. This is the
  product's surface.
- **Lesson-memory schema** + the **policy-updater** proposal flow (how a rule
  change is proposed, reviewed, accepted).
- **How "quality" is judged** for self-learning (verification passing is the
  floor; a human/learner grades beyond it).

---

## 8. The bottom line

We are not building a coding agent with governance bolted on. **Governance is
the agent** — an intelligent, business-editable risk/cost layer around a brain,
enforced to be dependable, recorded to be visible, and looped to **get better
every run**. That steadfaste-ness — same good result, over and over, rising with
use — is the product.