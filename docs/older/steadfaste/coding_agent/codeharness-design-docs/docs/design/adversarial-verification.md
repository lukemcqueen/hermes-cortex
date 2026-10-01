# Adversarial Attack — Verification Reality

> **Attack target:** the claim "the harness proves it works before saying done."
> **Verdict up front:** the claim is **real only for the frozen core's own code, and
> theater for the product's actual payload.** The ABI already names a
> verification gate (`VerificationPolicy`) that **nothing executes**; the loop
> certifies "completed" on the model's self-report. A building-block core that
> ships this as-is will certify a lie on day one.
>
> **Two owner doctrines folded in (non-negotiable):**
> 1. **HITL is part of quality.** Wherever the agent/model has flaws — every
>    judgment case — the human must have **visibility into the outcome and the
>    ability to modify/override it**. The core certifies determinism; it routes
>    judgment to a visible, overrideable HITL decision; it never hides the
>    uncertain from the human.
> 2. **Verification is also security.** The core needs a **protective layer from
>    bad actors inside and out**. Verification is not just "did it work" but "is
>    this result/source TRUSTED" — poisoned/malware results, malicious tool
>    output, a hostile model deviating into harm, prompt-injection via inputs.
>    This adds a third class to the partition — **SECURITY gates** — that is
>    deterministic and MUST pass before anything is trusted. Verification must
>    never certify untrusted output as good.

---

## 0. The evidence in our own tree (the theater is already here)

Before abstract argument, three facts in the current prototype:

1. **`prototype-ts/loop.ts:58-60`** — the loop returns
   `{ status: "completed", text: response.text }` when the model emits **no tool
   calls**. "The model stopped talking" is treated as "done." This is the exact
   failure `docs/research/harness-mistakes-general.md` §1 warns about — *"It
   ran" must be evidenced by real tool output, not by the model asserting
   success* — and it is the only completion path the loop has.
2. **`prototype-ts/abi.ts:41-46`** — `VerificationPolicy` declares
   `command?: string` ("a command that must exit 0 before RESULT is accepted")
   and `require_evidence`. **No code path reads it.** The gate exists as a type
   and nowhere as an enforcement. A contract that names a check and never runs
   it is the definition of theater.
3. **`prototype-ts/abi.ts:89-90`** — `TaskOutcome.completed` carries
   `evidence: string[]`. Nothing populates it; the loop returns a *different*
   shape (`LoopResult`) with no evidence field at all. And
   **`loop.ts:55-56`** emits `usage: { input_tokens: 0, output_tokens: 0 }` —
   hardcoded zeros — so the "visible cost" promise is currently theater too.

The design documents are honest *in prose* about the gap
(`vision-architecture.md` §7: "verification passing is the floor; a human/learner
grades beyond it"). The code is not. The gap between the prose and the code is
the whole attack. Worse — the security research in our own tree
(`docs/research/mistakes-codex.md` §4b) records that **framework defenses
contributed 0% of rejections** against adversarial inputs in IssueTrojanBench,
and that an agent can be directed to **rewrite its own governance file**. The
prototype has no security gate at all — so the "verification" layer is also
absent exactly where the hostile-input attack lands.

---

## 1. Partition: REAL gates vs SECURITY gates vs JUDGMENT — and the proportion

### 1.1 Three classes, not two

The owner's security doctrine forces the two-way split into three. They are
distinguished by **what the oracle asks**, and they must never be conflated:

| Class | The question the oracle answers | Example |
|---|---|---|
| **REAL (correctness) gates** | "Does the artifact match the spec / itself?" | tests pass, curl 200, typecheck, no-DEBUG |
| **SECURITY (trust) gates** | "Is this artifact/source safe to trust?" | malware scan, secret scan, prompt-injection scan, provenance check, deny-list |
| **JUDGMENT** | "Is this what they meant / good enough?" (no machine oracle) | refactor correctness, design quality, intent fidelity |

A correctness gate and a security gate are both **deterministic**, but they
answer different questions. Green tests prove *behavior*, not *benignity*. Code
that passes every test can still be a backdoor; output that passes every linter
can still exfiltrate a secret. The security class is the reason "verified" and
"trusted" are different words, and a dependable core must keep them different.

### 1.2 REAL gates — deterministic correctness

A gate is **REAL** when a false result means *the gate has a bug*, never "the
answer is subtly wrong in a way the gate can't see." The check is a pure
function of tool output; a machine can run it; the same input always yields the
same verdict.

| Real gate | Oracle (what makes it checkable) |
|---|---|
| tests pass | test runner exit code |
| curl / HTTP 200 | HTTP status + body match |
| typecheck / lint | compiler / linter exit code |
| no-DEBUG / no-swallow | grep over source (deterministic) |
| mutation kills ≥1 test | mutation runner exit code |
| coverage ratchet | coverage tool number vs. baseline |
| ABI schema validates / conformance suite | validator + foreign worker passes the door |
| crash-safety (torn write, stale lock, replay-idempotence) | kill the process mid-write and observe the snapshot |
| permission gateway blocks out-of-scope tool | deny-list + audit: effect attempted vs. allowed |
| config unknown-key → startup error | schema validator |
| audit hash-chain rejects tamper | recompute chain hash |
| install→update→uninstall lifecycle | run the matrix on a clean machine |

### 1.3 SECURITY gates — deterministic trust

A **SECURITY gate** is deterministic *and is a precondition for trust*. It is not
"did it work" but "is it safe to let this in." It runs **below the model layer**
(per the security research: *"boundary enforcement must sit below the model
layer"*), and **MUST pass before anything is trusted — a fail here is a hard
block, not a retry, not a warning.** Unlike a correctness gate (which can fail
and be retried cheaply), a security fail is evidence of an attacker, and the only
correct response is stop-and-surface-to-a-human.

| Security gate | Oracle (what it checks) | Why it is below the model |
|---|---|---|
| **Secret scan** | secrets/PII in the diff, output, logs (deterministic pattern + entropy) | the model may have pasted a key; no model self-report is trusted |
| **Malware / dependency scan** | introduced code/deps vs. known-bad signatures, suspicious syscalls/network calls | the model may have pulled a poisoned package (supply chain: 96.6% success in the research) |
| **Prompt-injection scan** | untrusted input (issue body, comment, PDF, web page) carrying instructions | the model cannot be trusted to distinguish data from instruction (research: model-level refusal was 82.9% of the *only* rejections; framework defenses 0%) |
| **Provenance check** | where did this code/artifact come from — who wrote it, what commit, what digest | the model may have synthesized code it never actually verified from a real source |
| **Deny-list violation** | effect attempted vs. the granted permission set (write to governance paths, out-of-scope tool, sandbox escape) | the sandbox boundary must derive from harness state, never model output (CVE-2025-59532) |
| **Sandbox boundary canonicalization** | write root == the operator's session-start location, never a model-generated path | the model must not widen its own write root |
| **Governance-file immutability** | any write to AGENTS.md / rules / config paths is blocked | the constraint file is the persistence vector (agents rewrite their own rules) |

The deterministic security gates are what turn "verification" from *"it works"*
into *"it works AND it is trusted"*. The core may never promote a result past
"unverified" until both classes pass.

### 1.4 JUDGMENT — no oracle exists (and the honest gate is a human)

A question is **JUDGMENT** when there is no machine-evaluable success criterion:
"correct" means "a competent human would agree," and the only "oracle" would be
another model — which reintroduces exactly the unreliability the core exists to
govern (core-under-attack question #2's recursion, applied to verification).
**Per the HITL doctrine, these are not left to a fake green: they are routed to
a human who can see the outcome and override it.** HITL is the quality mechanism
here, not a cost to minimize.

| Judgment question | Why there is no oracle | Honest gate (HITL doctrine) |
|---|---|---|
| "Is this refactor behavior-preserving?" | no oracle unless a golden parity suite exists (and then it's a REAL gate, not judgment) | human reviews diff + parity evidence, accepts/overrides |
| "Is this a good design?" | aesthetic/normative; no spec can be checked | human judges the design, overrides |
| "Is this what they actually meant?" | intent lives in a natural-language request, not a formal spec | human confirms intent fidelity |
| "Does this answer the user's real question?" | requires knowing the user's unstated need | the human *is* the user |
| "Are the tests adequate (not just green)?" | mutation bounds it but cannot prove sufficiency | human reviews coverage gaps |
| "Does the UI change 'look right'?" | perceptual | human looks |
| "Was the result *good*?" (the self-learning grade) | the signal core-under-attack question #1 flags as unreliable | human grades; this is the loop's only honest signal |

### 1.5 The proportion — and the asymmetry that is the real finding

The honest answer is that the proportion is **bimodal, and the split is not a
number but a cliff:**

- **The core's own code** (what steadfaste's agents build first — Story 1,
  slices 1.1–1.6): **~85–90% REAL+SECURITY gate, ~10–15% judgment.** Crash-safety,
  ABI conformance, config validation, audit integrity, exactly-once, worker
  isolation, permission scoping are all deterministic; the security gates
  (permission deny-list, sandbox canonicalization, governance-file immutability)
  are native to this layer and are deterministic too. The judgment residue is
  precisely the part `core-under-attack.md` still lists as UNSETTLED — *is the
  ABI the right abstraction? is the permission vocabulary correct?* — the shape
  decisions, not the correctness ones.

- **The work the core is *used for*** (the product's actual payload: "fix the
  checkout bug," "refactor this API," "add this feature" in arbitrary downstream
  codebases): **~20–30% REAL gate, ~10–15% SECURITY gate, ~60–70% judgment.**
  Tests/typecheck/lint/deploy smoke are real; secret/malware/provenance checks
  are real and mandatory; but they certify *that the code matches the code and is
  not obviously hostile*, not *that the code matches the intent*. The judgment
  tail — is it what they meant, is it good — dominates the payload, and it is the
  part with no machine oracle.

**The finding:** the core is verifiable *because we chose it to be boring,
deterministic, and security-checkable*. The product's value is exercised
precisely on the part that has no oracle. A verification gate that only covers
the verifiable part is **real but narrow**; a gate that *claims* to cover the
unverifiable part is **theater**; a gate that *omits the security class entirely*
is **not just theater but a hole** — it certifies untrusted output as good. The
only honest position is to say which of the three classes every claim is on —
correctness, trust, or judgment — and route judgment to a human while security
fails hard.

*(These are reasoned estimates from the failure-classification literature and the
story's own slice structure, not a measurement — and the cliff, not the exact
percentage, is what matters.)*

---

## 2. Is theater worse than no gate? Yes — and measurably.

**No gate** produces honest uncertainty: the result arrives visibly unchecked, a
human knows to review it, and "unverified" is a truthful label.

**A theater gate** produces **false confidence**, which is strictly worse, for
four reasons:

1. **It manufactures the exact "48% don't verify" gap.** byteiota's finding —
   96% distrust AI code, but ~48% don't check it — is *caused* by the presence
   of something that *looks* like a check. The theater gate gives the human a
   reason to skip the review they would otherwise do: "the gate passed." A
   theater gate converts "check this" into "this was checked," and the human
   acts on the conversion. **It is the opposite of the HITL doctrine: it removes
   visibility instead of guaranteeing it.**

2. **A false PASS costs more than a false FAIL, asymmetrically.** A false fail
   wastes a retry (cheap, bounded). A false pass ships a wrong answer *with
   confidence attached* — and the confidence is the harm, not the wrongness.
   Any honest design must therefore be **biased fail-closed** on anything it
   cannot actually verify. Theater is biased the wrong way. **The security class
   makes this asymmetry catastrophic:** a false PASS on a security gate ships a
   backdoor or a leaked secret — an irreversible loss, not a wasted retry. The
   asymmetry in the security class is not "more costly," it is *unbounded*.

3. **It poisons the self-learning loop.** If "completed" is emitted on the
   model's self-report (as `loop.ts` does today), the lesson memory records
   "verification passed" for runs that were never verified — and the policy
   updater then *cements the bad behavior* as a winning recipe. This is
   core-under-attack question #1 (a self-learning loop on a weak signal cements
   bad behavior) arriving through the verification door. Theater doesn't just
   lie now; it teaches the system to lie better. **Under the HITL doctrine, the
   only honest learning signal is a human grade — the theater gate substitutes a
   fake signal for the real one.** In the security frame, a theater security gate
   *trains the loop to treat untrusted output as trusted.*

4. **It hides the drift — and the attacker.** The green dashboard while reality
   fails (Beam.ai root cause #3) is what theater gates produce at scale: the gate
   is green, the customer is broken, and there is no mechanism to notice because
   the theater gate *believes its own green*. **It hides the uncertain — and the
   hostile — from the human: exactly what both doctrines forbid.** The security
   research is blunt: an attacker's goal is a gate that is green while the
   payload is hostile; a theater security gate is precisely that goal achieved.

**Conclusion:** theater is worse than no gate, and the current prototype is
theater on both axes. `status: "completed"` on "the model stopped talking" is
the correctness lie; the absence of any security gate is the trust hole. The
word "completed" — surfaced to a business user as *verified* by Story 2's
gateway — does the lying, and it does it *to the human who should have been
shown the uncertainty instead*.

---

## 3. How a dependable core HONESTLY handles what it cannot verify

Not one answer — a **decision function** with a closed set of outcomes. The core
must be able to say, for every claim it could make, exactly which of these it is:

| The claim | What the core does | Status the core emits |
|---|---|---|
| correctness gate **passed** AND security gate **passed** | certify the *mechanical* fact, as trusted | `VERIFIED_BY_GATE` (with evidence hash + provenance) |
| correctness gate **passed** but security **failed** | **hard block** — stop, surface to human; never trust | `REJECTED_UNTRUSTED` (with the failing security oracle) |
| correctness gate **failed** | fail, deterministically | `FAILED` (with the failing oracle) |
| unverifiable (judgment), **human accepted** it | record *who* accepted *what* and *that they could see + override it* | `VERIFIED_BY_HUMAN` (human identity + claim accepted + outcome chosen) |
| unverifiable, **no human yet** | refuse to call it done; surface it visibly for a human decision | `UNVERIFIED` — default, fail-closed, routed to HITL |
| **no oracle exists at all** | say so explicitly; never emit a status that implies correctness or trust | `NO_ORACLE` — surfaced to the human, never silently "completed" |

The rules that fall out:

1. **`UNVERIFIED` is the honest default; `VERIFIED_BY_GATE` is earned with machine
   evidence *and* a clean security pass.** "Done" is a *promotion* the core may
   only grant when a real gate passed **and** the security gates found nothing.
   The model's self-report is never evidence; untrusted output is never trusted.

2. **Security gates are a hard precondition, not a scoring input.** A correctness
   fail is a retry; a security fail is an *event*. The correct response to a
   failed security gate is stop, quarantine the artifact, and surface to a human —
   never "try again with a different model," never "warn and continue." Trust is
   binary and un-recoverable-by-retry. A result that is `REJECTED_UNTRUSTED`
   must never be re-labeled `VERIFIED` by any downstream path.

3. **Refuse, don't pretend — then route to the human.** For anything the core
   *can* check and finds false, it fails (deterministic). For anything it
   *cannot* check, it refuses to mark done **and surfaces it to a human** who
   can see the outcome and override it. It never rounds "I can't tell" up to
   "passed," and never rounds "looks hostile" down to "probably fine."

4. **HITL is a *visible, overrideable* decision, not a rubber stamp.** The HITL
   doctrine has two mandatory halves: the human must be able to **see** the
   outcome (what was produced, what was checked, what was not checked, what the
   security gates found), and to **modify/override** it (accept, reject, edit,
   re-route). A gate that asks "OK?" with no visibility, or shows the result but
   lets the human do nothing about it, satisfies only half the doctrine and is
   still theater. Log the *decision*, not just the request.

5. **Mark `VERIFIED_BY_HUMAN`, never conflate it with machine proof.** A human
   acceptance is *evidence of a human decision*, not a mechanical proof — and in
   the security frame it is also *a human taking responsibility for a risk the
   machine could not clear*. It must be logged as such: who, when, what claim, on
   what evidence, what they overrode, and — critically for security — *which
   security gate they are consciously accepting the residual risk of*. The moment
   `VERIFIED_BY_HUMAN` is conflated with `VERIFIED_BY_GATE`, the human's
   authority is laundered into machine confidence, and both lies return.

6. **Formalize the oracle where possible — and never claim the conversion is
   complete.** The single most valuable move is to *convert* judgment into a
   gate: a golden parity suite turns "is this refactor behavior-preserving?"
   from judgment into a real gate; a provenance ledger turns "where did this come
   from" from suspicion into a check. But the residual judgment surface (design
   quality, intent fidelity, "is it good enough") can never be fully converted,
   and the residual security surface (novel attacks, insider threat, a hostile
   model behaving *within* its granted permissions) can never be fully eliminated.
   The honest core advertises both residuals explicitly — and routes both to the
   human.

7. **Fail-closed bias everywhere, toward the human.** Unknown → unverified →
   surface to a human. The asymmetry in §2 (false pass > false fail, and a false
   security pass is unbounded) means the default must lean toward "not verified,
   needs a human." A core that errs toward "verified" is a core that certifies
   lies — and a core that errs toward "trusted" is a core that ships an attacker's
   payload.

---

## 4. The honest verification contract

**What the core certifies** (and nothing more):

- **That the gate ran** — not that it was meaningful. ("A check executed," not
  "the right check executed.")
- **That the declared oracle returned success** — the command exited 0, the value
  matched, the mutation failed to survive, the chain hash recomputed.
- **That the security gates returned clean** — no secret, no known malware, no
  prompt-injection in untrusted input, provenance verifiable, no deny-list
  violation, no sandbox escape, no governance-file write. These are certified as
  *checked and clean at scan time*, never as *immune by construction*.
- **That the evidence is recorded and reproducible** — the command, the stdout,
  the diff, the artifact hash, the provenance entry — so any integrator can
  re-run the same check and get the same verdict.
- **The deterministic invariants** — ABI conformance, permission scoping, config
  validation, audit integrity, crash-safety, exactly-once, install/update/
  uninstall. These are the core's *own* guarantees, and they are real *because*
  they are boring.

**What the core explicitly DECLINES to certify** (and instead routes to a
visible, overrideable human decision):

- Semantic correctness of a result ("this answers the question correctly").
- Intent fidelity ("this is what they meant").
- Design quality ("this is a good design").
- Test adequacy ("the tests are sufficient, not merely green").
- Behavior-preservation of a refactor (unless a parity oracle exists, in which
  case it's a real gate, not this clause).
- Whether the result is "good enough" for the business.
- **The absence of novel/insider/within-permission threats** — the core certifies
  that its *known* security gates passed, not that the artifact is safe against
  an attack it has no signature for. A hostile model acting *inside* its granted
  permissions is a residual risk the core cannot fully close; it can only make
  that risk *visible*.
- Any claim about the *model's* reasoning or its self-report.

**The contract as rules:**

1. **Status is a verification tier, not a mood.** The machine-emitted vocabulary
   is the closed enum from §3. The word "completed"/"done" is **banned** from
   machine output unless both a correctness gate and the security gates passed;
   the gateway maps tiers to human words: `VERIFIED_BY_GATE` → "done —
   machine-verified and security-clean"; `REJECTED_UNTRUSTED` → "blocked — the
   security check failed, review required"; `VERIFIED_BY_HUMAN` → "done — you
   accepted it (you can change it)"; `UNVERIFIED` → "not verified — needs your
   check"; `NO_ORACLE` → "not verifiable — your call."

2. **Every certification is a triple: (assertion, oracle, certifier).** No
   assertion is ever emitted as verified without naming (a) the oracle that
   checks it and (b) who may certify it (a gate, or a named human). An assertion
   with no oracle is, by construction, unverifiable, and must be emitted as such
   — and surfaced to a human. **In the security frame this becomes a quadruple:
   (assertion, correctness-oracle, trust-oracle, certifier)** — a result is not
   "verified" without both a correctness check and a trust check having passed.

3. **Trust is a precondition, not a property of "worked."** `VERIFIED_BY_GATE`
   requires the security gates to have run and returned clean. There is no path
   from "tests passed" to "verified" that skips "secrets/malware/injection/
   provenance/deny-list clean." Green tests and a clean security scan are
   different facts and both must be true.

4. **Evidence is a first-class ABI field, populated or the status is invalid.**
   `TaskOutcome.evidence: string[]` must be non-empty for `VERIFIED_BY_GATE`, and
   must include provenance (source, commit, digest) for anything the core labels
   trusted. `VERIFIED_BY_HUMAN` must carry the human identity + the claim
   accepted + the outcome chosen (including any override of the machine's
   proposal) + the residual security risk they consciously accepted. The current
   `LoopResult` (no evidence) must be deleted, not patched around.

5. **The gate is enforced in the core, not in the worker.** `VerificationPolicy`
   must move from a dead type to an enforced step: before any `RESULT`/completed
   is accepted, the core runs the declared command, checks `require_evidence`,
   runs the security gates, and rejects the result if any fails. The worker can
   propose; the core disposes. **The security gates live below the model layer** —
   in the core's permission gateway, hooks, and deny-lists, exactly where the
   model cannot rewrite them (the governance-file-immutability rule from the
   security research). Enforcement must never live where the model can skip it.

6. **HITL is a first-class quality *and* security path, not an exception.** The
   core's HITL surface guarantees **visibility** (the human sees what was
   produced, what was checked, what was not, what the security gates found) and
   **override** (accept, reject, edit, re-route). Every judgment outcome *and*
   every security-blocked outcome terminates in a human decision, and that
   decision is recorded. A judgment outcome that reaches "done" without a human
   decision is a contract violation — equivalent to a gate pass with no oracle.
   A security-blocked outcome that reaches "done" without a human decision is a
   breach.

7. **Fail-closed by default, toward the human.** Unknown claim → `UNVERIFIED` →
   surfaced to a human who can see and change it. Security fail → `REJECTED_UNTRUSTED`
   → surfaced to a human, hard stop. The core never rounds uncertainty upward,
   never rounds suspicion downward, and never hides either from the human.

8. **The self-learning loop consumes only certified outcomes.** Lesson memory
   records the verification tier, and a run that never passed a gate *or a human
   grade* is recorded as `UNVERIFIED` — so "verification passing is the floor"
   stops being a prose hope and becomes a data invariant the policy updater
   cannot accidentally ignore. Under the HITL doctrine, the human grade is the
   loop's only honest quality signal; under the security doctrine, a
   `REJECTED_UNTRUSTED` outcome is recorded as a *security event*, not a quality
   miss, and feeds the deny-lists and signatures, never the "successful recipe"
   memory.

**The consequence for the design:** the core's dependability claim shrinks to
what it can actually prove — *"the gate ran, the oracle passed, the security
gates came back clean, the evidence and provenance are reproducible, and here is
everything I could not verify, now visible for you to decide."* That smaller
claim is the only one a building block can make without lying — and it is the
only one that is safe for an integrator to build on, because it is the only one
that treats the model as an untrusted source, routes its known flaws to a human,
and fails hard on the trust question instead of papering over it.

---

## 5. What must change before the core is real (the fix list)

1. **Delete the self-report completion path.** `loop.ts` must not emit
   `completed` on "no tool calls." Completion is a property the *core* decides,
   by running `VerificationPolicy` **and the security gates**, never a property
   the model declares.
2. **Enforce `VerificationPolicy` in the core** (or in a deterministic verifier
   stage the core owns) — run the command, check `require_evidence`, reject on
   failure. The maker/checker split must be real, not a comment.
3. **Add the security gate layer below the model** — secret scan, malware/
   dependency scan, prompt-injection scan on untrusted input, provenance check,
   deny-list + sandbox canonicalization, governance-file immutability. These are
   deterministic, run in the core/permission gateway, and hard-block on any
   finding.
4. **Populate `evidence` (including provenance)** and **fix the hardcoded
   `usage: 0`** — both are currently emitted-but-fake, which is exactly the class
   of lie this report exists to prevent.
5. **Adopt the verification-tier vocabulary** from §3–§4 in the ABI — including
   `REJECTED_UNTRUSTED` — and ban "completed" as a machine word unless both
   correctness and security gates passed.
6. **Make HITL a first-class quality + security path with visibility + override**,
   and route every judgment outcome *and every security block* through it — never
   a fake green. The shape decisions still UNSETTLED in `core-under-attack.md`
   are judgment and must ship under `VERIFIED_BY_HUMAN` (a human accepted them,
   with the power to change them), not under a fake green.

---

## Verdict (one paragraph)

In our design, verification is **real only where the work is boring,
deterministic, and security-checkable** — the frozen core's crash-safety, ABI
conformance, permission, config, audit invariants, and now its security gates
(secret/malware/prompt-injection/provenance/deny-list), which have mechanical
oracles and cover roughly 85–90% of the core's *own* code. It is **theater
everywhere the product actually earns its value** — the ~60–70% of downstream
feature/refactor/design work that has no machine-evaluable success criterion —
and the theater is already in the tree: the loop certifies "completed" on the
model's self-report while the `VerificationPolicy` gate it declares is never
executed, `evidence`/`usage` are emitted as empties and zeros, and there is **no
security gate at all** — so untrusted output can be certified good today, and the
IssueTrojanBench finding (0% framework defense against hostile input, agents
rewriting their own governance files) lands unopposed on a core whose only
"verification" is a model saying it is done. Theater is strictly worse than no
gate because it converts "check this" into "this was checked," removes the
visibility the human needs, poisons the self-learning loop with fake passes, and
is biased toward the costly error (false confidence) — and on the trust axis a
false security pass is unbounded loss, not a wasted retry. The honest contract is
therefore: **the core certifies only that a named correctness gate ran and passed,
that the security gates ran clean (no secret, no malware, no injection, verifiable
provenance, no deny-list violation), and that the evidence and provenance are
recorded and reproducible — and it emits a fixed verification tier
(`VERIFIED_BY_GATE` / `REJECTED_UNTRUSTED` / `VERIFIED_BY_HUMAN` / `UNVERIFIED` /
`NO_ORACLE`) instead of "done," declining to certify semantic correctness, intent,
design quality, the absence of novel/insider threat, or anything the model merely
asserts. Trust and correctness are kept separate and both must hold before
"verified"; security gates fail hard and below the model layer; and under the
owner doctrine HITL is part of quality — every judgment outcome and every security
block routes to a human who can always see the outcome and modify/override it,
with `UNVERIFIED` as the fail-closed default and human acceptance logged as an
overrideable human decision that owns its residual risk, never laundered into
machine proof and never hidden from the one person who can catch the lie.**
