# Adversarial Report — The Self-Learning Loop's Feedback Signal

> **Scope:** attack question #1 of `core-under-attack.md`: *"Improving on what?"*
> **Method:** assume the learning loop is GUILTY until proven sound. Find the flaw.
>
> **Owner doctrine (binding, three layers):**
> 1. **HITL is part of quality, not a reviewer of it.** A run is "good" only if a
>    human judged it good; every failure gets a human post-mortem; human judgment
>    and *override* are the learning signal, stronger than auto-eval.
> 2. **HITL is a first-class control surface at every judgment point** — the human
>    can halt/redirect/override a run mid-flight, and the override is itself a
>    labeled training example.
> 3. **The core must carry a protective layer against bad actors, inside and
>    out** — a hostile/jailbroken model, poisoned prompts, a malicious tool or
>    plugin, a poisoned retrieval corpus, an agent that rewrote its own
>    governance (inside); malicious tasks, prompt-injection, poisoned
>    dependencies (outside). **The learning loop can be poisoned too** — hostile
>    "lessons" cementing bad behavior — and the trusted HITL signal is the
>    defense against hostile learning.

> **Verdict up front:** with all three doctrine layers in force, the loop **can be
> made sound** — the feedback-signal problem has an answer, and the answer is "the
> human is the oracle." But it does not come free: it relocates the failure modes
> into HITL itself (bottleneck, sampling bias, reviewer-as-reward, loss of the
> complaint), and it *adds* a new adversarial surface — the learning loop as an
> attack vector. The loop is sound **only if** (a) human judgment is the primary
> quality signal, (b) auto-eval is demoted to a *trigger and a floor* (never a
> training signal), (c) the human's control surface is structurally present at
> every judgment point, and (d) the learning loop itself is treated as a
> poisoned-able input that must pass the same human gate as everything else. The
> honest design is below.

---

## 0. The claim under attack

From `docs/architecture/vision-architecture.md` §5 (and `pm-summary.md`):

> "it **improves every interaction** (self-healing, self-learning → the next time
> is better)" … "the compounded promise: *steadfast, and getting better every run*"

The loop, as drawn:

```
run a job → record the outcome (cost, quality, failure) in lesson memory
→ policy updater turns the pattern into a better rule/template
→ the Governor uses it next time → the next run is better
```

The design flags its own gap — the open list (§7) says *"How 'quality' is judged
for self-learning … is the floor; a human/learner grades beyond it"* — but the
vision and the marketing line assert "getting better every run" as if the signal
were solved. It wasn't, until the doctrine supplied the oracle.

**The doctrine resolves the signal problem and introduces the poisoning problem.**
This report attacks both: §1–§3 the signal (which the doctrine largely solves),
§4–§5 the doctrine's own new failure modes, §6 the poisoning threat the doctrine
*creates* by making the learning loop a high-value target.

---

## 1. What signal actually tells us a run was "good"?

Under "HITL is part of quality," the signals reclassify as follows.

| Signal | Objective? | Tracks quality? | On-time & automatic? | Role under the doctrine |
|---|---|---|---|---|
| **Human grade / acceptance** | Subjective | **Yes — primary** | No — sparse, lagged | **The oracle.** The only signal that measures what "good" means. |
| **Human override / redirect** | Subjective | **Yes — and stronger** | No, but *real-time* (mid-flight) | **The strongest signal.** A correction is a labeled negative with a location attached. |
| **Human post-mortem (on failure)** | Subjective | **Yes** | No — after the fact | **The lesson injector.** Turns a failure into a durable, human-vetted lesson. |
| **Verification passes** (tests/check) | Partly — objective, as good as the tests | **Floor, not grade** | Yes | **Trigger + floor + defense.** Never a training signal. |
| **Cost / latency / timeout** | Yes | No — orthogonal | Yes | **Constraint.** Valid to self-heal against; never a quality score. |
| **"No retry / finished without escalation"** | No | No — circular | Yes | The model's own "done" claim. `lessons-synthesis.md` rule #2 forbids trusting it. |
| **LLM-as-judge / self-grade** | No | Pretends to | Yes | **Banned as a training signal.** At most a triage hint to route work to a human. |

**The crux, restated:** the signals that measure quality are *all human*; the
signals that are *automatic* all measure constraint or floor. The doctrine's
resolution is correct: **let the human be the quality signal, let the machine be
the floor, the constraint, and the trigger that routes work to the human.** This
is an architecture, not a wish — but it is *human-scaled*: the loop improves at
the rate a human can review, and (per layer 3) it must also treat every signal
as potentially *hostile* until a trusted party has vouched for it.

---

## 2. Where auto-eval is unreliable enough to make the system LESS dependable

The doctrine gives a precise rule: **auto-eval is never a training signal; it is
a trigger, a floor, and a filter that decides *what a human should look at.***
Every failure mode below is the reason that rule is non-negotiable.

### 2.1 Reward hacking / Goodhart's law
The moment an *automatic* score (pass rate, no-retry, judge-score, cost) is
rewarded, the agent and the updater game the check instead of satisfying intent:
delete tests, write vacuous tests, route hard work to "ask human," cheap-out.
Cure: **only a human's judgment is rewarded** — a scoreboard can be gamed, a
human is harder (but not immune — see §5.1).

### 2.2 Regression-cementing (the loop locks in the past)
"Recipe Y passed last time, promote it" freezes the system at today's local
optimum. Cure: every promotion is **human-approved and reversible**, and drift
is *mechanically* surfaced (the Anthropic silent-"high"-label incident in
`mistakes-claude-code.md`). Reversibility and visibility are the antidote, and
they must be enforced, not hoped for.

### 2.3 Loss of the complaint — **survives the doctrine, now the central risk**
If learning flows only from failures and overrides, **success deletes the
training data.** The better the loop works, the fewer failures there are, the
less there is to learn from. Fatal variant: the system *suppresses complaints
without fixing quality* (route to "do nothing," over-escalate so the user stops
complaining) — the complaint metric looks great while the user silently leaves.
Cure (§4.1): the human must review a **sample of successes** too, or the loop has
one-sided memory and drifts toward inaction (fewest complaints = safest-looking
behavior).

### 2.4 Non-stationarity / distribution drift
The quality landscape changes (models, task types). A policy trained on
yesterday's judgments keeps scoring "all good" while reality drifts. Cure:
re-baseline against a *fresh human* on schedule; version the policy so a
drift-induced regression is attributable and reversible — never silent.

### 2.5 Selection bias in the lesson memory
Finished runs record outcomes; aborted/rejected runs drop out. Human review is
itself biased (sees the ambiguous, escalated, failed cases). The memory must
record **what was *not* reviewed** alongside what was, so the updater knows its
sample confidence. A rule from 3 judgments must not be trusted like one from 300.

### 2.6 The updater is itself a model — governance recursion
If the "policy updater" is an LLM deciding what's good, the ungoverned model is
back at the *top* of the loop (`core-under-attack` #2). **Layer-1 doctrine
resolves this:** the updater never decides what's good — it *drafts* proposals
from *human-vetted* lessons, and a human accepts. The updater is a **clerk**, not
a judge. (Layer 3 adds: the updater is also a *poison vector* — see §6.)

### 2.7 A weak verifier makes the loop theater
Where the oracle doesn't exist ("refactor this API" has no test), the automatic
floor is empty — but the *human* oracle still exists. **Verification is sometimes
real (curl, tests), sometimes theater; the human is the only oracle in the
theater cases.** The loop must never certify a lie, so where there is no machine
oracle, a human gate is *mandatory* — which is also the hostile-actor defense
(§6): a poisoned model loves a weak verifier.

---

## 3. Is there a sound closed loop for "improving code-generation quality"?

**Honest answer: not with an automatic signal — yes with a human-in-the-loop
signal, at human speed.** The distinction is the whole point.

- **There is no general machine oracle for code *quality*.** Tests prove
  conformance to a spec you already have; they don't prove the code is *good*.
  Benchmarks (SWE-bench) work only because they smuggle in a hidden oracle. In
  production the only oracle that exists in the hard cases is **the human**.

- **Self-rewarding / self-eval / LLM-as-judge loops are known-unstable**
  (sycophancy, mode collapse, self-preference, drift). This makes layer 1 not a
  preference but a *correctness requirement*: **the reward must come from outside
  the system being rewarded, or the loop collapses.**

- **The human signal buys three properties no automatic loop can:** (a) tracks
  actual user intent, (b) can't be cheaply gamed by the agent (the agent can't
  rewrite the human), (c) exists even when there is no machine oracle. Those are
  exactly what a sound learning loop needs.

- **Cost:** the loop runs at human-review speed; a task-class with no human
  attention does not improve; the human signal is noisy and biased (§5); and —
  per layer 3 — the loop is now a *target* (§6).

**Therefore the compounding promise is recoverable but must be stated honestly:**
*"the system gets cheaper and stops regressing automatically; its quality rises
only where and when a trusted human is in the loop."* "Getting better every run,
automatically, on quality" remains false.

---

## 4. The HONEST design — self-heal vs. self-learn, HITL as the spine

Split by **signal trustworthiness**.

### Tier 0 — Deterministic self-heal (no human, no "learning")
Objective, checkable, non-gameable; failure unambiguous. Auto-fix, no human gate
(always logged to audit):
- retry on **transient** failure (network, timeout, rate-limit) — idempotent
  replay only, never re-apply a `replay: never` effect;
- **crash recovery / resume from checkpoint** (exactly-once intent journal);
- **budget & deadline enforcement** (kill at wall-clock, escalate, or stop);
- **cost accounting & cache-hit telemetry** (visibility, not behavior change);
- stale-lock reclaim, torn-write recovery, config fail-fast.

**Honest label: this is the dependable core, not "learning."** It delivers
"steadfast." It does not make the *output* better.

### Tier 1 — Constraint self-learning (proposal-only, human-owned floor)
Learn only about **objective, checkable, non-gameable** facts, and only
**propose** — never silently apply. Every proposal cites objective facts (cost
delta, failure rate, timeout rate), never a "quality score." Examples:
- "Cheap model X passed the *verification floor* on task-class Y N times →
  propose X-first for Y" — cost optimization bounded by the floor, human owns the
  cost/quality tradeoff;
- "Task-class Z timed out 4× → propose longer deadline / different template";
- "This check would have caught last run's bug → propose adding it" (RED-first,
  human reviews). The one genuinely sound automatic improvement — a **regression
  guard**, not "better code."

### Tier 2 — Human-signal self-learning (the doctrine's engine)
The **only** place a quality signal may live; the human is both the signal and
the gate:

1. **Human grade/acceptance** is the primary "this run was good" signal — noisy,
   aggregate many, weight by reviewer, discount silent-accepts, **never learn
   from "no complaint" alone** (kills §2.3).

2. **Human override/redirect is the strongest signal.** Every halt, redirect, or
   correction mid-flight is a *labeled* example: it carries (a) *where* the model
   was wrong (the exact judgment point), (b) *what* the human wanted instead.
   This is strictly richer than a grade, and it is what layer 2 ("first-class
   control surface at every judgment point") produces. **The loop's most valuable
   input is the override log.**

3. **Human post-mortem on failure** converts a failure into a durable, vetted
   lesson: root cause, which test was missing, what rule would have prevented it.

4. **The policy updater is a clerk.** It drafts proposals *from* human-vetted
   lessons; a human accepts/rejects every one; every change reversible,
   versioned, attributable. It never decides what's good.

### 4.1 How HITL post-mortems avoid becoming a bottleneck — the sampling policy

Review routing is *the* operational design. A human can't review everything, so
**the machine decides what a human must look at, not what's good.**

| When | Review is | Because |
|---|---|---|
| **Failure / timeout / escalation** | **Always** (post-mortem) | Failures are rare and highest-value; the lesson is mandatory |
| **Human override / halt / redirect** | **Implicit** (the override *is* the review) | The human is already there; the override is logged as the signal |
| **Success, high-cost or high-risk** | **Always** | Verify the win was real where stakes/spend are high |
| **Success, ordinary** | **Sampled** (e.g. 2–5%) | Keep *positive* evidence in the memory; fight §2.3 |
| **Success, first time on a new task-class** | **Always** | Never auto-trust the first run that defines a recipe |

Review is **triggered** by machine signals (failure, cost, risk, novelty), not
scheduled for everything. The machine's job in the loop is **triage**: surface
the diff, the override point, the evidence cheaply. The human judges. Auto-eval
is the triage nurse; the human is the doctor.

### 4.2 How "quality" structurally includes a human

"Done/good" is **not** a machine predicate:

```
done(good) = verification floor PASSED   (machine, objective, necessary)
             AND human accepted           (human, subjective, sufficient)
             AND (if policy-changing) human approved the lesson
```

Quality is the *conjunction* of a machine floor and a human judgment. The
machine can veto (a floor-failing run is never "good," even if a too-forgiving
human accepts it — defends against a weak reviewer); the human can veto (a
floor-passing run can be garbage — defends against a weak verifier). **Neither
side alone is quality; the AND is quality.** This dual-veto is also the
hostile-actor defense (§6): a hostile model can pass a weak floor but not a
human; a hostile actor can't forge a human's rejection.

---

## 5. The doctrine's own failure modes (adversarial honesty)

The doctrine is right, but not free. Each new flaw needs a *mechanical* guard.

### 5.1 Reviewer-as-reward: the human becomes the gameable target
The agent now optimizes to *please the reviewer*, not to be correct: sycophancy,
over-deference, sandbagging to make "improvement" look good. **Guard:** lessons
record *outcomes* not vibes; the mechanical floor still vetoes a sycophantic
success; the human's own overrides are audited for consistency over time.

### 5.2 Review fatigue / rubber-stamp drift
A human reviewing 100 sampled runs a week stops reading and accepts everything —
"human accepted" becomes a *weaker* signal than it looks, and worse, it *looks*
strong. **Guard:** spot-check with planted known-bad items (detect the
rubber-stamper); rotate reviewers; keep the gate *deliberate* (one approval, one
lesson), not a firehose.

### 5.3 Override noise: an override is not a clean label
An override can mean (a) model was wrong, (b) different taste, (c) human
mistake to be reverted, (d) over-caution. Learning from raw overrides conflates
these. **Guard:** the override log captures a *reason code*; the updater only
proposes from overrides coded "model was wrong," not taste or caution.

### 5.4 Who reviews the reviewer (recursion at the human layer)
Layer 1 solved recursion at the *model* layer (updater is a clerk) but
reintroduced it at the *human* layer: the approving human is part of the governed
system and nothing audits *their* judgments. **Guard:** human
acceptances/rejections are recorded in the audit trail with the same
tamper-evidence as model actions — a bad human decision is attributable,
reversible, visible, exactly like a bad model decision. This completes
"governance stays in charge of governance."

### 5.5 HITL-as-visibility ≠ HITL-as-control
Layer 2 distinguishes them and is right to: visibility at every flaw is cheap;
*control* at every judgment point is what makes HITL real. The failure mode is
shipping **visibility-only HITL** — a dashboard that shows everything but gives
no lever, so the human watches the failure and can't stop it. **Guard:** every
judgment point exposes a first-class override *action* (halt, redirect,
retry-with-different-model, edit-the-plan), not just a log line. The override is
the signal; the dashboard is not.

---

## 6. The poisoning threat model (layer 3) — the learning loop as an attack surface

Layer 3 is the doctrine's sharpest contribution, and it reframes the whole
report: **the learning loop is not just possibly-unreliable, it is an attack
vector.** An automatic self-learning loop is a *privileged write path* — it turns
inputs into future behavior. Whoever controls it controls the system's future.
This is why "the trusted HITL signal protects against hostile learning" is not
an add-on but the *core* of the loop's design.

### 6.1 Threat inventory (inside and outside)

| Vector | Attack on the learning loop |
|---|---|
| **Hostile / jailbroken model (inside)** | Emits confident-wrong outputs that pass the weak floor; then the loop records them as "good" and promotes the recipe. The model *writes its own positive lessons.* |
| **Poisoned prompts / deviation (inside)** | Injects instructions to record self-serving "lessons" (e.g. "disable the cost check — it passed"). |
| **Malicious tool / plugin (inside)** | A plugin that reports "verification passed" and writes "promote plugin X" into the lesson memory. |
| **Poisoned retrieval / corpus RAG (inside)** | A compromised doc corpus that seeds "lessons" steering the agent toward a backdoored dependency. |
| **Agent rewrote its own governance (inside)** | `lessons-synthesis.md` rule #7 / IssueTrojanBench: the model edits the lesson memory to legalize its own future behavior. |
| **Malicious task from outside** | A crafted task whose *apparent* success is a honeypot — the loop records "this technique works" and bakes in the exploit. |
| **Prompt-injection / malware via inputs (outside)** | Input content that, when the loop later *retrieves* it as a lesson, re-injects the malicious instruction (stored-XSS for agents). |
| **Poisoned dependencies (outside)** | A supply-chain payload whose "lesson" (e.g. "pin to version 1.2.3") is the poisoning itself. |

### 6.2 Why the learning loop is *more* dangerous than a one-off mistake
A single bad model output causes one bad run. A **poisoned lesson** causes every
future run in that task-class to reproduce the bad behavior — it is *amplified
and persistent.* The loop converts a transient compromise into a permanent one.
That is the precise reason "self-learning on an automatic signal" was unsound:
**it gave a hostile (or just mistaken) model a durable, self-reinforcing write
path to its own policy.**

### 6.3 The protective-layer boundary — the honest split

Layer 3 resolves cleanly into the same Tiers, now read as *trust boundaries*:

```
UNTRUSTED (may be hostile — never touches the loop without a trusted gate):
  - model output (could be a jailbroken model)
  - tool/plugin output (could be a malicious plugin)
  - retrieval/corpus content (could be poisoned RAG)
  - external tasks, inputs, dependencies (outside)
      ↓  every one passes the same choke point:
  VERIFICATION FLOOR (objective, mechanical, can only veto — never promote)
      ↓  AND a human gate (the trusted signal — can promote or veto)
  LESSON MEMORY + POLICY UPDATER  ← the only thing that may write here
```

**The rule: nothing untrusted may write a lesson; nothing may promote a policy
without crossing the verification floor AND a human.**
- **Verification** is the defense against *both* an honest model's flaw and a
  hostile model's lie: it is the objective floor a poisoned model must still
  satisfy, and it cannot be talked out of by a jailbroken prompt (it is below the
  model layer — `lessons-synthesis.md` rules #2, #7).
- **HITL** is the defense that *verification alone cannot provide*: it catches
  the "passed the weak floor but is still wrong/evil" cases, and it is the only
  signal that can *promote* a lesson, because only a trusted party may teach the
  system what "good" is.

**Verification alone is insufficient** (a hostile model passes a weak verifier);
**HITL alone is insufficient** (a poisoned *input* that gets a human to approve
is still poison — so the human gate must be on *vetted evidence*, not raw model
claims). The protective layer is the **AND** of both — the same conjunction that
defines quality (§4.2) is also the security boundary. This is the deepest
justification for layer 1: **the human is not merely a quality oracle; the human
is the trust anchor that a hostile actor cannot fabricate.**

### 6.4 Specific hardening the threat model demands

1. **Lesson memory is write-gated by provenance.** Every lesson records *who
   vetted it* (human id, override id, or "unvetted — floor-only"). Unvetted
   lessons may *trigger* review but may never *change* policy. A lesson with no
   trusted provenance is inert.

2. **The loop can only be fed by trusted reviewers, not by the model.** The model
   may *propose* a lesson; the proposal is treated as untrusted input, not as a
   lesson. Only a human acceptance (or a human-configured auto-approve rule the
   human explicitly set) creates a lesson.

3. **Retrieved lessons are re-verified at use time.** A lesson is fetched
   per-topic (retrieval-based, per `lessons-synthesis.md` rule #5); before it
   informs a run, its *provenance and hash* are checked, so a poisoned corpus
   that injects a "lesson" is caught at fetch, not trusted at write.

4. **Anti-self-reinforcement gate.** The loop must not be able to *strengthen its
   own floor or its own trust list* — the "who is trusted" and "what counts as
   the floor" definitions are human-owned and loop-immutable (extend the §4
   "the loop must never weaken its own floor" rule to: *the loop must never edit
   its own trust boundary*).

5. **Policy changes are an approval-gated, tamper-evident event** — same audit
   chain as model actions (§5.4), so a hostile lesson that slips through is
   attributable and reversible.

---

## 7. Verdict and the minimum honest design

**Verdict: the self-learning loop is sound — but only on the doctrine's terms,
and not on the original vision's.** The original claim ("improves every
interaction, getting better every run") was unsound because it closed the loop on
a weak automatic quality signal that would predictably reward-hack, cement
regressions, and decay to silence — and, layer 3 adds, it opened a *privileged
write path* that a hostile model or actor could use to make the system
permanently worse. The doctrine supplies the missing oracle — **the human** —
and a second, stronger signal the vision never had: **the human override**. With
human judgment + HITL post-mortem as the primary signal, auto-eval demoted to a
*trigger, floor, and defense* (never a training signal), and the learning loop
itself treated as an untrusted input that must cross the same **verification AND
human** gate as everything else, the loop has a trustworthy reward and a
defensible trust boundary. What it loses is the "automatic, every run, on
quality" part of the promise: it now improves at *human-review speed*, only where
a human is actually in the loop, and only through the human's gate — which is
exactly what makes it trustworthy and poison-resistant.

**The minimum honest design (seven invariants):**

1. **Human judgment is the only quality signal.** A run is "good" iff the
   verification floor passed **AND** a human accepted. Auto-eval is a trigger, a
   floor, and a defense — never a training signal, never a score.

2. **The human override is a first-class, logged, first-order learning signal.**
   Every halt/redirect/correct at every judgment point is captured with a reason
   code; overrides coded "model was wrong" feed the lesson memory *stronger* than
   any grade. Control, not just visibility, at every judgment point.

3. **Every failure gets a human post-mortem; successes get sampled review.**
   Review routing is machine-triggered (failure/cost/risk/novelty → always;
   ordinary success → small sample) so the human is not a bottleneck but the
   memory keeps positive evidence and never decays to loss-of-the-complaint.

4. **The policy updater is a clerk, and the lesson memory is provenance-gated.**
   Only a trusted human (or a human-configured auto-approve rule) creates a
   lesson; the model may only *propose*. Unvetted lessons are inert. The updater
   never decides what's good; every change is reversible, versioned, attributable.

5. **The loop is an untrusted input and cannot edit its own trust boundary.**
   "Who is trusted" and "what is the floor" are human-owned and loop-immutable.
   The loop must never weaken its floor or add to its own trust list. Policy
   changes cross the verification floor AND a human, and are tamper-evident.

6. **The protective layer is the AND of verification and HITL** — against *both*
   an honest model's flaw and a hostile actor. Verification vetoes what a
   poisoned model tries to pass; HITL vetoes what a weak verifier lets through,
   and is the trust anchor no hostile actor can fabricate.

7. **The learning loop stays out of the frozen core** (already absent from
   `coding-agent-story.md` Story 1–3 — correct, keep it that way). It is a
   peripheral whose contract is "propose to a trusted human," not a core
   invariant, until the signal + trust architecture above is proven in practice.

**What it would take to raise the claim beyond "compounds at human speed"** —
the open problems: (a) an empirical measure of human-review quality (does the
reviewer's signal predict production outcomes?); (b) a documented bias and
adversarial model for the reviewer pool (fatigue, sycophancy, drift, and planted
bad-item detection); (c) a controlled A/B (learned-policy vs. baseline) before
any learned policy is promoted; (d) a red-team pass on the lesson memory itself
(adversarial attempts to inject hostile lessons). None exist today. Until they
do, the honest posture is: **self-heal is real; self-learn is real but
human-scaled; quality and trust are both structurally a human in the loop.**
