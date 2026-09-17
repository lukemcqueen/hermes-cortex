# The Core + Core Interfaces — Attack Findings

> **The keystone, under attack.** We attacked the core design from four angles
> (self-learning, governance recursion, the ABI, verification reality) plus two
> owner doctrines that landed mid-flight (HITL-as-quality, protective-layer from
> bad actors). The point was to find the flaws — and we did, including several
> already present in the tree. **The core is not designed until it survives this.**
> Detail in the four `adversarial-*.md` reports; this is the consolidated
> vulnerabilities list.

## What the attack exposed (the honest inventory)

### 1. The self-learning loop is UNSOUND as originally claimed
- **"Improves every interaction / getting better every run" is a false
  over-claim.** A closed loop on an automatic "quality" signal predictably
  reward-hacks, cements regressions, and decays to "loss of the complaint."
- It also opened a **privileged write path** a hostile model/actor could poison
  (hostile "lessons" cementing bad behavior).
- **The fix (the doctrine): the human is the only quality signal** — grade +
  post-mortem (mandatory on failure) + override (the strongest signal, a
  location-tagged "the model was wrong here"). Auto-eval is demoted to *trigger,
  floor, and defense — never a training signal*.
- **Self-heal is real** (deterministic: cost, timeout, retry). **Self-learn is
  real but human-scaled** — and it must stay OUT of the frozen core.

### 2. Governance recursion is a category error — but was about to ship
- The docs' phrase **"cost/method intelligence" in the Governor conflates two
  things**: *cost* is a deterministic rule (safe, no model); *method* is the
  Brain's job. Keep them separate or an ungoverned model ends up above the
  policy.
- **Partition is exact:** Governor = total deterministic function (constraints
  in → policy out); Brain = all judgment *inside* the policy; **the human**
  decides what matters.
- **"Who watches the watcher"?** Three layers: (1) watcher's rules frozen +
  unreachable by the model; (2) every decision visible + overridable by the
  human as an active control surface; (3) the core is a security boundary the
  model cannot rewrite. Control flows one way: **human → core → model.**

### 3. The ABI is not ready — it has real, in-tree defects
- **Lineage unquestioned:** the "11 events / 6 ops" vocabulary is Pi's loop
  re-expressed as wire events — the core claims worker-agnosticism while
  describing one specific turn-based worker.
- **"Task" is the wrong unit.** The primitive is a **job** (invocation) with
  opaque input/result; telemetry collapses to one `progress` + a registry; ops
  drop to the essentials.
- **Policy is smuggled.** `Budget`/`ModelPolicy`/`VerificationPolicy` are the
  Governor's *volatile* output, but the current ABI ships them frozen to the
  worker — governance on the wrong side of the trust boundary. It must be
  core-owned and referenced by `policy_id`, not carried.
- **Most damning — it's not even one artifact:** Rust and TS "same" ABIs already
  disagree on 4 wire shapes; Rust's serde can't parse TS frames. A frozen
  contract that isn't one contract is a promise with no proof.
- **Missing the HITL + protective primitives:** no `needs_human`, no `deny`, no
  taint, no capability-scope — despite the earlier decision.md demanding them.

### 4. Verification: real only at the core, theater for the payload — and already shipped as theater
- **Three classes, not two:** REAL correctness gates (deterministic tests/curl/
  typecheck) · SECURITY trust gates (malware/secret/injection/provenance,
  below-the-model, hard-block) · JUDGMENT (no oracle → human).
- The core's own code is ~85–90% gate/security; the **payload it's used for is
  60–70% judgment** — which the core currently certifies as "done."
- **In-tree theater right now:** `loop.ts` returns "completed" the moment the
  model stops talking; `VerificationPolicy` is declared but **never executed**;
  `evidence` and `usage` are empty/zero; **no security gate exists**. Untrusted
  output can be certified good today.
- **The fix:** a five-tier status (`VERIFIED_BY_GATE / REJECTED_UNTRUSTED /
  VERIFIED_BY_HUMAN / UNVERIFIED / NO_ORACLE`) — never a bare "done." Core
  certifies only the deterministic + security invariants with reproducible
  evidence; everything judgment and every security block routes to a visible,
  overrideable human who owns the residual risk. `UNVERIFIED` fails closed.

---

## The consolidated design consequences (what the core must now BE)

**A) The frozen core is the security boundary and the trust boundary.**
- Mechanical deny-list + least-privilege-by-default + tamper-evident audit +
  approval gates a jailbroken model / malicious plugin / poisoned corpus cannot
  rewrite from inside. HITL is both governance and the anti-bad-actor gate (the
  only element that can distinguish an *attack* from an *error*).

**B) Verification is a contract, stated honestly.**
- The core certifies *only what it can prove* (deterministic gate ran + security
  clean + reproducible evidence/provenance). It declines semantic correctness /
  intent / design quality / novel threat — routing those to a human. It NEVER
  certifies a lie; `UNVERIFIED` is an honest state, not a failure to hide.

**C) HITL is a first-class interface, not an add-on.**
- The ABI carries `needs_human` (event) and `human_decided` / `direct` (ops) so
  any worker/integration speaks HITL natively. The human can halt/redirect/
  override at every flaw/judgment point, and the override is itself the
  strongest learning signal. Post-mortems on failure are mandatory and HITL.

**D) The learning loop is out of the frozen core and human-gated.**
- Lesson memory is provenance-gated (unvetted lessons inert); the policy
  updater is a *clerk*, not a judge, and can't edit its own trust boundary.
  Self-heal (deterministic) is core; self-learn (human-scaled) is peripheral.

**E) The ABI must be rebuilt, correctly.**
- Frozen frame + versioned ignorable content + capability/scope handshake.
  Ops: `start/direct/human_decided/deny/cancel/kill` · Events:
  `started/needs_human/progress/result/failed(+class)/stopped`. Policy
  core-owned via `policy_id`. JSONL-over-stdio frame is fine; the JSON *content*
  must not be prematurely frozen, and it must be ONE interoperable artifact.

---

## Verdict (honest)

The core is **not** designed yet. We have a strong *thesis* and now a long,
specific list of what must be true. The good news: the flaws are **findable,
fixable, before freeze**, and several were caught *in the tree* (theater
verification, wire disagreement, smuggled policy). A building block must earn
its dependability — this attack is how it starts. **Next: rebuild the ABI to
the corrected design (E), enforce the verification contract (B), and make HITL +
the protective layer first-class (C/A) — then re-attack.** Uncertainty is still
the point until it survives all of it.