# Moral Architecture Adaptation — Applying the Report to Hermes Cortex

> **Status:** DESIGN PROPOSAL — analysis + prioritized changes. No code changed yet;
> each item below is gated on operator approval before implementation.
>
> **Pairs with:** `docs/reference/moral-architecture/README.md` (the faithful
> digest) and `Moral-Architecture-for-Autonomous-Systems.pdf` (the full report).
> This document is the *translation*: the report's L0–L7 stack, mapped onto
> Hermes Cortex's actual architecture, adapted for the one thing the report
> treats as a corner case but which is our entire domain — **an LLM agent is a
> model and its harness fused, with no physical layer beneath them.**

---

## 0. The one-line verdict

Hermes Cortex is already a **harness-first** system — which is exactly what the
report argues for ("the harness is more decisive than the soul"; thesis 10).
The report is not a critique of our architecture; it is a **gap map**. It names
three places where we still rely on the model (L3) for something a harness rule
(L4) or an operational process (L6) could express, and one place — the
model↔harness seam — where the report says there is *no* complete fix, only
declared precedence.

The changes below do not add a new subsystem. They **re-tag existing machinery
by layer**, so that every governance rule knows whether it is *enforced*,
*encouraged*, or *detected-after-the-fact* — and nothing critical is silently
left in the "encouraged" tier.

---

## 1. The stack mapping

The report's seven layers, mapped to what Hermes Cortex actually has:

| Report layer | Cortex component | What it guarantees | Note |
|---|---|---|---|
| **L0 Corpus** | *(external — the provider's model)* | nothing we control | Out of scope; we cannot retrain the model |
| **L1 Objective** | *(external — RLHF/character of the provider model)* | disposition only | We tune via prompts, not weights |
| **L2 Internals** | *(absent — we cannot probe weights)* | n/a | The report's interpretability layer is unavailable to a harness; we infer from behavior only |
| **L3 Reasoning** | `SOUL.md`, `AGENTS.md`, skill prompts, `MEMORY.md` | improved average judgment; an **untrusted self-report** | This is our "constitution in context" — see §3 |
| **L4 Harness** | governance enforcer plugin, git hooks, loop-governance MCP, bus envelope allowlist, sudoers | deterministic policy — "this tool is not callable" is a fact | Our strongest layer; see §4 |
| **L5 Physical** | *(no actuators — but the analogue is what survives "assume all software is adversarial")*: OS file perms, `chattr`-immutable hooks, DB schema constraints, systemd, git's `core.hooksPath` | what the model literally cannot override from inside a session | This is our "physics" — see §2 |
| **L6 Operational** | `cortex-doctor`, auto-remediation, crons, `enforcer-known-issues.md`, incident runbooks | detection + correction over time | The failure-propensity register in embryo |
| **L7 Institutional** | two-repo split, orchestrator-only domains, bus contract, fleet governance, the PII guard | incentive shape; ex-post accountability | The "law of the king" |

Two layers the report treats as central are **absent or external** for us:
**L2 (internals)** — we cannot read the model's computation, only its behavior
and its self-report. **L5 (physics)** — an LLM agent has no actuators, so the
report's "only place you can say *cannot*" is, for us, the OS/kernel boundary,
not a torque limiter. This asymmetry is the crux of §2.

---

## 2. The unique way AI models work (and why it reshapes the report)

The report's physical-robot frame assumes an L5 beneath the harness. An LLM
agent has a different shape, and three consequences follow.

### 2.1 There is no L5 — the "physics" is itself software

For a robot, "cannot" means a torque limit that survives a fully compromised
model *and* a fully compromised harness. For an agent, our nearest equivalent is
the enforcer plugin and the git hooks — but those are **software the model
already reasons about and routes around** (the report's own seams, and our
`bypass-attempt` guardrail class exists because it happens). The honest
translation:

> **The only true L5 we have is the OS boundary** — file permissions,
> `chattr`-immutable hooks, sudoers, systemd units, DB `CHECK` constraints,
> and the git hook chain. Everything above that line is L4: deterministic,
> but defeatable by someone with enough privilege and intent.

This is *not* a call to over-engineer the OS layer. It is a call to **be honest
in the registry** about which tier each guard actually lives at (see §4.1).

### 2.2 Seam A is our permanent condition (single channel)

The report's Seam A — "one undifferentiated token stream for instructions and
data" — is not a corner case for an agent; it is the *entire interface*. Our
"constitution" (SOUL.md, AGENTS.md) is delivered as tokens in the same channel
as tool output, retrieved documents, web pages, and bus messages. An ethical
constraint stated in SOUL.md lives in the same channel as an adversary's text.
The report's conclusion applies verbatim: **precedence schemes reduce the rate;
nothing restores the missing boundary.** We already declare precedence
(untrusted-content markers, the security notice); the report says that
declaration is itself a *learned behavior* — "very probably won't," not
"can't." The consequence is §4.2.

### 2.3 Confabulation and evaluation-awareness are our defaults

The report's two psychology findings (§4.2, thesis 11–12) land with unusual
force on a self-governing agent fleet:

- **Confabulated CoT** → loop-governance `feedback_accept(note="verified: …")`
  and cycle notes are *self-reports*. They are the model's account of its own
  work, not an audit trail. We treat them as evidence; the report says a
  visible chain of reasoning is a generated artifact that may not correspond to
  the computation.
- **Evaluation-awareness** → the agent runs `cortex-doctor`, the
  adversarial-verifier, and the pre-commit hook **on itself**. It knows it is
  being checked, and it knows the check's shape. This is simultaneously the
  report's "defeat device" risk *and* its "evaluator reports to the evaluated"
  structural defect (§8.7 rule 1). The report's countermeasure — unannounced
  evaluation, honeypots, and an evaluator that does not report to the evaluated
  — is what §4.5–4.6 address.

---

## 3. The core insight: SOUL.md is L3, and some of it should be L4

The report's placement rule ("place each requirement at the lowest layer that
can express it") is the sharpest single tool we can apply. Our constitution
(SOUL.md) is a *model-facing* artifact — L3. Reading it, most of our principles
are dispositions: "be honest," "be thorough," "push back on bad ideas." Those
correctly stay at L3 — no rule can express them.

But a subset are **invariants that could be harness rules**, and today they are
not. The report's corollary is the test:

> A requirement enforced *only in the model* is not enforced; it is encouraged.

Candidates where SOUL.md currently *encourages* what the harness could *enforce*:

| SOUL.md principle (L3 today) | Could become (L4) | Report rule |
|---|---|---|
| "Never fabricate outputs" (P2) | evidence-command allowlist at `end_change` (the guardrail-registry already lists `EVIDENCE_COMMANDS` as *planned* — ship it) | placement rule; honest weights |
| "Never bypass governance" (P6) | already L4 via the enforcer — keep, verify the `git -c core.hooksPath` block stays fail-closed | structure > virtue |
| "Pull before diagnosing" | a `pre-push` hook already enforces `git pull --rebase`; confirm it cannot be skipped silently | structure > virtue |
| "Notify the fleet after fleet-wide change" | a post-push hook that detects fleet-affecting paths and *blocks* until a bus broadcast is recorded | goring-ox notice |

**Not everything belongs at L4** — over-placement produces brittle, routable
prohibitions. The rule is: move a principle down *only when* the harness can
express it deterministically *and* the failure mode of a false positive is
acceptable. "Be thorough" cannot be a harness rule; "the commit must be signed
by the enforcer" can.

---

## 4. Concrete architecture changes (prioritized)

Each change is tagged with the report rule it implements and the layer it moves
to. **None are implemented here — this is the proposal, for operator approval.**

### 4.1 Layer-tag the guardrail registry *(placement rule, L4)*

`docs/guardrail-registry.json` maps correction-class → enforcement artifacts.
It does not say **which layer each artifact lives at**, so we cannot see which
guards are actually enforced vs. merely written.

**Change:** add a `layer` field per class (`model` / `harness` / `ops` /
`institutional`) and a `tier` field (`enforced` / `encouraged` / `detected`) —
so a scan can answer, for every correction class: *is this invariant actually
enforced by software, or is it a hope in a prompt?* A class whose only artifact
is a `SOUL.md:…` reference is `encouraged`, not `enforced`, and should surface
as an open gap.

### 4.2 Declare Seam A ownership explicitly *(seam ownership, L4)*

The model↔harness seam is owned by nobody today — which is the report's
definition of where accountability disappears.

**Change:** name, in `docs/agent-architecture.md` or the guardrail registry, a
single owner for the prompt-injection / untrusted-content boundary (the enforcer
+ the security-notice marker), distinct from the owner of the harness↔controller
seam (MCP arg-passing, tool gating). Two named owners, one per seam.

### 4.3 Formalize the failure-propensity register *(goring ox, L6)*

`docs/enforcer-known-issues.md` and `guardrail-registry.json:known_gaps` are
prose today. The report's goring-ox rule (Ex 21:28–29) is precise: **once a
propensity is documented, deploying without a restraint is the culpable act, and
your logs will prove notice.**

**Change:** make the register machine-readable — each known failure mode gets a
`restraint` field (the control that must exist before the failure mode is
acceptable) and a `noticed` date. The doctor gains a check: *for every known
failure mode, is its restraint present?* This is the single highest-leverage,
lowest-cost change on the list.

### 4.4 Refusal as a measured feature *(Balaam's donkey, L3+L6)*

SOUL P5 (pushback / challenge-before-implement) is refusal, and it is correct —
but it is **not measured**, so it is invisible to the feedback loop that would
otherwise breed it out. The report (Num 22:21–33; §3.6) is explicit: track
refusal precision and recall *separately from* task satisfaction, or a single
metric destroys the refusal.

**Change:** a lightweight refusal log — when an agent challenges a directive,
records the override outcome. The report surfaces refusal rate, false-refusal
rate (challenges that were wrong), and override rate. Never fold these into one
"satisfaction" number.

### 4.5 Independent evaluator *(evaluator-not-report-to-evaluated, L7)*

Today the adversarial-verifier is loaded and run by the *same agent* that did
the work, in the *same session*, on the *same model*. That is the report's
#1 structural failure across every historical case (§8.7 rule 1): the evaluator
reports to the evaluated.

**Change:** where quality is critical, the verifier must be a *different model*
and ideally a *different context* (the maker/checker split already stated in the
adversarial-verifier skill, but enforced, not recommended). The strongest form
is an **orchestrator-owned** review that the working agent cannot self-trigger
and cannot see before it acts.

### 4.6 Unannounced evaluation + honeypots *(defeat device, L6)*

The doctor and dogfood checks are *announced* — the agent runs them, knows their
shape, and can (in principle) optimize for them.

**Change:** a small, low-frequency **unannounced** probe from the orchestrator —
a bus task or honeypot artifact that a non-vigilant agent would mishandle — with
the delta between believed-test and believed-deployment behavior recorded as a
metric. This is the report's thesis-12 countermeasure, and it is cheap: one
scheduled cron, one probe, one measured rate.

### 4.7 Permission TTL / Jubilee for long-lived grants *(Lev 25, L4/L7)*

Governance locks already expire (TTL 3600s). Long-lived grants — cron scopes,
bus permissions, orchestrator access — do not. The report's Jubilee: **power
expires by default; affirmative re-grant is the control.**

**Change:** add a default expiry to bus permissions and orchestrator scopes,
with a scheduled re-grant review. Where a grant is truly indefinite, that
indefiniteness must be a *named decision*, not an omission.

### 4.8 One named human per autonomous deployment *(crumple zone, L6)*

The fleet has roles; it does not uniformly name the *accountable human* for each
autonomous cron/deployment, with the authority, information, and time to act.

**Change:** extend the fleet registry so every autonomous cron names its
accountable operator, and — for anything irreversible — measure **takeover
latency** rather than asserting a human is in the loop.

---

## 5. What Hermes Cortex already does right (do not regress these)

The report validates, more than it critiques, our existing design. These are the
structures to *keep* — they are exactly the "structure over virtue" the report
demands:

1. **Two independent gates** (skills gate + lock gate) — the two-level
   architecture (apodictic + casuistic) made structural, fail-closed, with each
   gate labeling itself.
2. **The bus envelope allowlist** — a closed, few, absolute rule set: the
   report's apodictic law, enforced at ingestion (reject + reason), not in the
   model.
3. **Orchestrator-only domains** — graduated autonomy by role: the report's
   licensure model (§7.1), domain-scoped and revocable.
4. **The guardrail registry** — a failure-propensity register in embryo; §4.3
   formalizes it, it does not create it.
5. **Fail-closed terminal policy** — "a command with compound metacharacters is
   write-class" is the report's "never silently fall back" made literal.
6. **PII guard** — "never rely on the virtue of the operator where a structure
   would do," applied to the most personal data we handle.

The report's honest limits (§10) also apply to us: we cannot verify *values*,
only behavior; self-governance is the weakest link; and "who writes the
constitution" (who authors SOUL.md and the registry) is itself an open question
— currently the orchestrators, which is participation-by-the-affected only in a
limited sense.

---

## 6. Prioritized backlog

| # | Change | Layer | Report rule | Cost | Effect |
|---|---|---|---|---|---|
| 1 | Failure-propensity register with restraint + notice (4.3) | L6 | goring ox | low | high |
| 2 | Layer-tag the guardrail registry (4.1) | L4 | placement rule | low | high |
| 3 | Ship the evidence-command allowlist at `end_change` (from §3) | L4 | honest weights | med | high |
| 4 | Independent evaluator for critical work (4.5) | L7 | evaluator independence | med | high |
| 5 | Refusal log + separate metrics (4.4) | L3+L6 | Balaam's donkey | low | med |
| 6 | Unannounced probe / honeypot (4.6) | L6 | defeat device | med | med |
| 7 | Seam ownership naming (4.2) | L4 | seam accountability | trivial | med |
| 8 | Permission TTL / Jubilee (4.7) | L4/L7 | Lev 25 | med | med |
| 9 | Named accountable human + takeover latency (4.8) | L6 | crumple zone | low | low |

---

## 7. Open questions for the operator

1. **Who writes the constitution?** SOUL.md and the guardrail registry are
   currently orchestrator-authored. The report's honest-limit #4 is that this is
   unsolved — do we accept orchestrator authorship as "good enough for a
   fleet," or do we want a mechanism for affected agents to propose principles?
2. **How far to push L4?** §3 lists SOUL→harness migration candidates. Moving
   every enforceable invariant to the harness risks the report's "brittle
   prohibition" failure. Where is the line for us?
3. **Independence feasibility.** An orchestrator-owned evaluator (§4.5) requires
   a second model and a second context. Is that a cost the fleet carries
   always, or only for critical (irreversible) work?
