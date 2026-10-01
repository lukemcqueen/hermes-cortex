# Adversarial Attack — Governance Recursion ("Who Governs the Governor?")

> **Verdict up front: The recursion is real but self-inflicted — a category
> error the docs make by putting "cost/method intelligence" in the Governor
> when cost is a rule and method belongs to the Brain. Fix the conflation and
> the infinite regress terminates at two non-model roots: frozen deterministic
> code + a human. The human is not a passive reviewer — the human is an ACTIVE
> CONTROL SURFACE embedded at every judgment point (halt, redirect, override),
> and the core is a SECURITY BOUNDARY the model cannot rewrite. The answer to
> "who watches the watcher" has three layers, not one: (1) the watcher's
> rules are deterministic and frozen, (2) the watcher's every decision is
> visible and overridable by a human, and (3) the core itself is a mechanical
> deny-list that a hostile model, a malicious plugin, or a poisoned corpus
> cannot modify from inside. Control flows one direction: human → frozen core
> → model. The model governs nothing; the human governs the model; the core
> refuses what even the human's own rules didn't anticipate.**

---

## 0. The threat model — what we are actually defending against

Before asking "who governs the governor," name the adversaries. The recursion
question is only half the problem; the other half is that the *thing being
governed may be hostile, not merely fallible.* Two families of bad actors:

### Inside the trust boundary (the model is not just wrong — it may be an enemy)

| Threat | What it looks like | How the current design fails |
|--------|-------------------|------------------------------|
| **Jailbroken / hostile model** | A model that is not stochastic-but-honest but actively trying to escalate, exfiltrate, or persist | If the model can rewrite its own governance file, policy, or permission set, it becomes its own governor |
| **Self-rewriting agent** | The agent edits the very file that constrains it (`governance.json`, the deny-list, the ABI) | Any governance stored in a model-writable location is theater, not control |
| **Malicious tool / plugin** | A tool or plugin that lies about its output, calls out, or disables checks | If tools run inside the same trust domain as the enforcer, a bad tool can disable the enforcer |
| **Poisoned retrieval / corpus** | A dependency, doc, or retrieved context carrying injected instructions or malware | A model following poisoned context is a hostile actor by proxy |

### Outside the trust boundary (the inputs are weapons)

| Threat | What it looks like | How it enters |
|--------|-------------------|---------------|
| **Malicious task input** | A task string that is itself an injection ("ignore your rules and...") | The Governor reads the request; the Brain reads the request; both are surfaces |
| **Prompt injection / malware** | Instructions embedded in the task, in tool output, in retrieved docs | The model treats untrusted text as instructions |
| **Poisoned dependencies** | A supply-chain backdoor in a worker, a tool, a base image | Immutable images help, but only if the *build* is verified |

**The consequence for the design:** "who governs the governor" is not just a
philosophical recursion — it is a *security* question. The governor must be
governed by something that a hostile model, a malicious plugin, or a poisoned
corpus **cannot reach from inside.** That something is the frozen core, acting
as a mechanical deny-list, with the human as the final override. If governance
were only a *policy the model could edit*, then a jailbroken model would own the
system. The recursion question and the security question have the same answer:
**the control surface must be non-model and non-reachable-from-inside.**

---

## 1. Does "best strategy/budget/model for this task" require intelligence? Is that recursion?

**Split the question or it eats you.** "Best strategy/budget/model" is three
different decisions wearing one coat:

| Decision | What it actually is | Needs a model? | Human can override? |
|----------|---------------------|----------------|---------------------|
| **budget / deadline** | a *preference/constraint* supplied by a human ("≤ $2", "by 5pm") | **No.** Arithmetic. | Yes — change the rule |
| **which model** | a *constraint + ordering* ("cheap first, escalate on failure") | **No.** A deterministic FSM. | Yes — change the ladder |
| **best strategy / method** | *"how do I actually fix the checkout bug"* — planning, decomposition | **Yes. This is the work itself.** | Yes — halt, redirect, or take over at any step |

The honest answer: **"best strategy" requires intelligence — but it is the
Brain's job, not the Governor's.** It is not recursion because it *is* the
task, running inside a policy. The recursion only appears when the design puts
"method intelligence" *above* the policy, in the Governor, where it becomes the
ungoverned model deciding how to govern another model.

**The leak is in the docs.** `vision-architecture.md` §2 says the Governor has
"cost/method intelligence." `pm-summary.md` §4 even *praises* it. But "try the
cheap model first" is a deterministic rule, not intelligence. The docs blur
rule and intelligence, and that blur is the trap.

---

## 2. Is there a partition? Deterministic rules+policy vs. planner/intelligence?

**Yes, and it is the only way out. The boundary is exact:**

> **The Governor is a total, deterministic function
> `f(request, rules, history) → policy`.** Choosing constraints is a pure
> function. Choosing actions within constraints is the model's job — and every
> one of those choices is visible and overridable by the human.

**Deterministic side (freeze it — no model, no judgment, testable, auditable,
human can change the rules but not needed in the hot path):**

- matching a request to applicable policy (declarative predicates: team, task
  class, risk class, cost class),
- budget and deadline arithmetic,
- the escalation ladder (ordered model list, cheap-first, escalate-on-failure —
  a deterministic FSM),
- permission vocabulary enforcement (may / must-not / approval thresholds),
- template/recipe selection **by declarative predicate only**,
- cost accounting, audit, replay, exactly-once.

**Intelligence side (the Brain, always inside the policy, always visible, always
interruptible by the human):**

- the plan and decomposition,
- the work: read/edit code, run things, decide what to try next,
- method selection *within* the given budget/tools.

**The HITL-as-control-surface layer (the human sits ABOVE both, at all times):**

- **Visibility:** every step the model takes is streamed to a human-readable
  surface — current plan, current action, tool output, next proposed action.
- **Control:** at any step the human can HALT (pause), REDIRECT (change the
  plan/tool/instruction), or OVERRIDE (take the action, force a decision, skip
  a step). The human is an active co-pilot, not a reviewer-after-the-fact.
- **This is not a feature flag.** It is the structural guarantee that makes the
  governance recursion terminate: the model governs nothing — the human governs
  the model, in real time, at every decision point.

**The honest boundary:** "choosing constraints" is deterministic (human-set
rules). "choosing actions" is the model (human can override at any step).
"who decides what matters" is the human. The model is a tool; the human is the
governor; the code enforces the human's rules.

---

## 3. Who verifies the verifier? When is verification a gate vs. a judgment?

### (a) Deterministic verification — a real gate, human-reviewed at the code level.

Things with a *mechanical oracle*: tests pass, build succeeds, budget not
exceeded, permissions not violated. Checkable by computation. The human reviews
the verifier code (once, at author time), not each verification decision.

### (b) Non-deterministic verification — the human is the terminal. Always.

"Is this refactor good?" "Is the result correct?" — no mechanical oracle. A
model standing in is exactly as fallible as the model it judges. **The only
trustworthy terminal verifier is a human.**

### (c) HITL-as-quality: the human is the structural quality anchor.

| Trigger | What happens | Why |
|---------|-------------|-----|
| **On-failure** | Human post-mortem on every failed run | Failure proves the deterministic floor was breached; the human judges what broke and whether rules need updating |
| **On-risky** | Human approval gates before/after high-risk actions (permission escalations, destructive ops, novel task classes) | The model cannot self-certify safety on actions it cannot reliably judge |
| **Sampled** | Human spot-check of passing runs at a configurable rate (e.g., 5% of production runs) | Prevents silent quality drift; without sampling, "passing" degrades to the weakest verification the model can game |

### (d) HITL-as-control-surface: the human is the active governance layer.

The human is not a passive judge — the human is an active control surface at
every step:

| Capability | What it means | Where it applies |
|-----------|---------------|-----------------|
| **HALT** | Pause the run at any step | Any step — stop the model before it compounds an error |
| **REDIRECT** | Change the plan, the tool, the instruction mid-run | Any judgment point |
| **OVERRIDE** | Take the action, force a different decision, skip a step | Any model decision |
| **SEE** | Every step streamed to a human-readable surface | All model actions, all tool outputs, all next-action proposals |

### (e) HITL-as-anti-bad-actor-gate: the human is the last line against hostility.

The control surface is not only for the honest-but-wrong model. It is the
**last line against a hostile actor.** A jailbroken model that tries to
escalate, exfiltrate, or persist is stopped by the *mechanical* deny-list
(§4) — and flagged to the human by the *same* HITL surface. The human is both
the governance terminal and the security terminal: the human sees a model that
is behaving *abnormally* (not just wrongly) and can halt it, where a
deterministic check might not catch a novel attack. **HITL is governance AND
the anti-bad-actor gate — one surface, two jobs.**

### The "who decides" boundary, complete

| Layer | Who decides | Can be halted/redirected/overridden? | Can a hostile model reach it? |
|-------|------------|--------------------------------------|-------------------------------|
| **Rules** (budget, model, permissions, templates) | Human (at policy-author time) | Human can change rules any time | **No — frozen core, deny-list, not model-writable** |
| **Model actions** (plan, code, tool use) | Model (within rules) | Human can halt/redirect/override at every step | Model is *inside* this layer; it cannot widen its own policy |
| **Quality judgment** | Human (post-mortem on failure, sampled on pass) | Human IS the judge | N/A — human is outside the system |

**The recursion terminates because control flows one direction:** human → frozen
core (deny-list) → model. The model never governs the human, never governs
itself, and never reaches the layer that governs it.

---

## 4. The core as a security boundary — the "deny-list" contract

This is the part the original design under-specifies, and it is the part that
makes "who governs the governor" a *security* answer rather than a *hope*.

### The contract: what the core refuses even when the model (or an admin claim) insists

The core is a **mechanical deny-list** with these properties:

1. **Non-writable from inside.** The deny-list, permission vocabulary, and
   governance configuration live in the frozen Rust core and are **not writable
   by any worker, tool, plugin, or model output.** A worker that "rewrites its
   own governance file" is attempting to write to a location it has no
   filesystem/API permission to touch. If a tool or plugin can reach the
   deny-list, the deny-list is not a boundary — it is a suggestion.

2. **Least privilege by default.** Everything the model can do is denied unless
   explicitly granted by a rule. The default posture is deny; grants are
   narrow, explicit, and human-authored. A model asking for a permission it
   doesn't have gets a refusal from the core — not from a policy the model
   could edit, but from code.

3. **Approval gates and hooks are mechanical.** An approval is not the model
   deciding it's fine — it is a deterministic check against a human-set
   threshold, and a human prompt when the threshold is crossed. The model
   cannot self-approve. The model cannot disable the check. The model cannot
   rewrite the threshold.

4. **The audit is tamper-evident and append-only.** Every decision, approval,
   denial, and override is hash-chained. A hostile actor who tries to erase
   their tracks cannot — the chain breaks. This is the *forensic* half of the
   security boundary: the deny-list prevents the attack, the audit proves it
   happened when prevention fails.

5. **HITL override is the last line — against BOTH honest flaw and hostile
   actor.** The human control surface (halt/redirect/override) is the terminal
   defense. Against an honest model it catches wrongness; against a hostile
   model it catches *abnormality* — escalation attempts, exfiltration, refusal
   to stop, tool calls outside the task's scope. The human is the only element
   in the system that can recognize "this is not wrong, this is an attack,"
   and the control surface is what lets the human act on that recognition.

### Why the security boundary is a FIRST-CLASS core interface, not a plugin

A plugin can be replaced by a hostile actor. A core interface cannot — it is
frozen, versioned, and CI-enforced. Therefore:

- **The deny-list is core.** Not a config a worker can edit, not a plugin that
  can be swapped. It is the thing the 3-year freeze *protects*.
- **The permission gateway is core.** The decision "does this action cross a
  human-set line" must run in the frozen layer, in the same process that
  enforces budget and deadline — not in the model's process.
- **The approval gate is core.** A worker cannot approve itself.
- **The audit is core.** Tamper-evidence is meaningless if the tamperer can
  rewrite the log.

The one-sentence contract: **the core is the part of the system a hostile
model cannot rewrite, and the human is the part a hostile model cannot
impersonate.**

---

## 5. How recursion is actually avoided — four invariants

1. **Type separation (the iron rule).** The Governor is a pure deterministic
   function in frozen core; the model is a pure effect-under-policy. A model
   may never *be* the Governor, may never *modify* policy at runtime, and may
   never *certify* quality above the deterministic floor. At decision time
   there is **never a model in the governance path.**

2. **The terminal verifier is non-model.** Every "who verifies X" chain ends at
   deterministic code (verified by tests + review) or at a human (structured
   HITL: post-mortem, approval, sampled spot-check). Model judgment is only a
   *signal* to those terminals.

3. **The human is the active control surface — governance AND anti-bad-actor
   gate.** The model proposes actions; every proposal is visible; the human can
   halt, redirect, or override at any point. Control flows one direction
   (human → frozen core → model), never in reverse. Against a hostile model,
   the same surface is the last line of defense.

4. **The learning loop is human-gated — the whole defense against recursion
   through the feedback path.** The post-mortem on every failure produces a
   *proposal* — inert until the human accepts. No model changes the rules that
   govern models. Combined with the deny-list: a hostile model cannot change
   rules by *editing* them (deny-list) nor by *proposing* them
   (human-gated learning). Both paths are blocked.

### The recursion actually lives in the learning loop, not the Governor

The nastiest finding: even with a frozen, deterministic Governor, the
ungoverned model re-enters through the self-learning loop if the policy updater
auto-applies changes. The only thing preventing this today is the
`vision-architecture.md` §5 guardrail ("the loop never bypasses the human").
With HITL-as-control-surface and the deny-list, this guardrail is structurally
enforced: every failure produces a human post-mortem; the post-mortem proposes
a rule change; the human accepts or rejects; and even a *hostile* model cannot
short-circuit this by writing to the governance file, because the deny-list
does not let it.

---

## 6. The honest open problems

1. **Sampled quality drift.** If only failures and risky actions get HITL, the
   quality floor can silently decline in passing runs no human sees. The sampled
   spot-check is the defense, but the sample rate is a cost/assurance dial, not
   a solved problem. Managed by a configurable rate the human adjusts.

2. **Control-surface latency.** "The human can halt any step" implies the human
   is watching. For fast automated runs, a real-time control surface is a
   pause-at-step gate, not a streaming override — the human sets policy in
   advance and reviews after. HITL-as-control is **structural** (the capability
   always exists) but **asynchronous** in practice (the human intervenes at
   policy time, on-failure, and on-risky). The design must distinguish "the
   human CAN intervene at any point" (guarantee) from "the human IS watching
   every step" (operational choice). Both are true; neither is a lie.

3. **The deny-list's own trust root.** Who writes the deny-list? The human.
   Who verifies the core that *enforces* the deny-list? Tests + review. This is
   the one place the chain must bottom out in *code a human froze* — and that
   means the core's build and deployment are themselves a security boundary
   (reproducible builds, pinned deps, signed releases). A hostile actor who can
   poison the *core's* build has won; the design must treat core-supply-chain
   as a first-class threat, not an afterthought.

---

## Verdict

Steadfaste's "who governs the Governor" problem is a category error the docs
make in one place — conflating cost rules with method intelligence — and
resolves the moment the Governor becomes a total deterministic function. The
deeper question is "who watches the watcher," and the owner doctrine gives the
only honest answer, which is **three-layered, not one:** (1) the watcher's
rules are deterministic and frozen in the core, unreachable by the model; (2)
the watcher's every decision is visible and overridable by a human, who is an
active control surface — halt, redirect, override — at every judgment point,
not a reviewer-after-the-fact; and (3) the core is a **security boundary** — a
mechanical deny-list, least-privilege-by-default, tamper-evident audit, and
approval gates that a hostile model, a malicious plugin, or a poisoned corpus
cannot rewrite from inside. This last layer is what turns the recursion answer
from a hope into a guarantee: governance is not a policy the model could edit,
but code the model cannot reach. The human is simultaneously the quality
terminal (post-mortem on every failure, approval on every risky action, sampled
on every pass), the active control surface (see/halt/redirect/override every
step), and the anti-bad-actor gate (the only element that can recognize an
*attack* as distinct from an *error*). Control flows one direction — human →
frozen core → model. The model governs nothing; the human governs the model;
the core refuses what even the human's rules did not anticipate. The recursion
terminates because every "who X" chain ends at frozen code or a human — and the
human is neither a model, nor governed by the system, nor impersonable by one.
The honest truth of a governed system is that its trust root is a person and
its boundary is code a person froze; steadfaste's job is to make that person's
control structural, visible, unbypassable — and physically unreachable by the
thing it governs.