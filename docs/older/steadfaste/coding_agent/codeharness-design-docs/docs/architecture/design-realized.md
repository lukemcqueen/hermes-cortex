# Steadfaste — The Design, Realized (with pictures)

> The whole system, visible at a glance. A business owner, an engineer, and an
> agent should each find here the one picture that explains the product. Words
> per `spec/covenant-vocab.md`; contract per `spec/core-spec.md`. This doc
> *realizes* the design — how the parts sit, talk, decide, and improve.

---

## 1. The whole system in one picture

```
   A STEWARD (human — cares for + is answerable for the system)
        │  "add a checkout fix, under $2"
        │  (via Telegram or the web screen)
        ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  THE CONSTITUTION  ← the dependable core (the supreme law)   │
   │                                                            │
   │  • reads the CHARTER (your rules): budget, model, tools,     │
   │    approvals · it gives THIS job a MANDATE                   │
   │  • commissions the AGENT, enforces the Mandate               │
   │  • verifies every step · records to the LEDGER               │
   │  • asks the STEWARD when unsure / risky / a judgment         │
   │  • retries, heals, never silently loses a job                │
   └──────────────────────┬───────────────────────────────────────┘
                          │  "run this job, within this Mandate"
                          ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  THE AGENT  (the governed actor — a Worker wrapped in the     │
   │              Charter + Mandate + Covenant)                   │
   │  plans · edits code · runs tests · calls the model            │
   │  streams "I'm doing X…" · seeks guidance when unsure          │
   └──────────────────────┬───────────────────────────────────────┘
                          │  "here's the result + the proof"
                          ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  THE LEDGER  (Postgres — the unchangeable record)            │
   │  every Mandate, step, verification, approval, cost — kept    │
   │  forever, auditable, replayable                              │
   └──────────────────────────────────────────────────────────────┘
```

**One sentence:** a **Steward** sets the rules in the **Charter**; the
**Constitution** turns one job into a **Mandate** and enforces it on the
**Agent**; the Agent does the work and **seeks guidance** when unsure; the
Steward **ratifies** or **vetoes**; every step lands in the **Ledger** — held
together by a **Covenant** of trust, and we verify everything before trusting it.

---

## 2. The layers (who sits where)

```
              ┌───────────────────────────────────────────┐
              │     THE CONSTITUTION (Rust core)          │
              │  govern · enforce · verify · record        │
              │  the unoverrulable law                     │
              └───────────────────┬───────────────────────┘
                                  │  the Covenant (wire)
              ┌──────────┬────────┴───┬─────────┬─────────┐
              ▼          ▼            ▼         ▼
          AGENT      WORKER      GATEWAYS    (future
          (ours,     (Claude,    Telegram    harnesses
          governed)  Pi, our    WhatsApp    plug in)
                     own —      (swappable)
                     swappable

   cross-cutting (all under the Constitution's watch):
     CHARTER  = rules you set        STEWARD = the accountable human
     LEDGER   = the record            COVENANT = the bond of trust
     GUARD    = the protective layer (below the model)
     LEARN    = the improvement loop (out of the core, stewarded)
```

### Swap-ability — the building-block property
```
            THE CONSTITUTION + COVENANT   ← what stays (steadfaste)
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   AGENT A        AGENT B         AGENT C
   (our own)     (a partner's)   (an integration)
        │              │              │
        ▼              ▼              ▼
   WORKER         WORKER         WORKER
   (Claude)       (Pi)           (our own)
        └──────────────┼──────────────┘
                        ▼
   any of these may be swapped; the Constitution governs whichever is plugged in
```

---

## 3. The life of one job (the flow, step by step)

```
 STEWARD                    CONSTITUTION                    AGENT
   │   "do X, ≤$2"               │                              │
   │────────────────────────────▶│  reads the CHARTER            │
   │                             │  gives a MANDATE              │
   │                             │── commission ────────────────▶│
   │                             │                              │ started
   │                             │◀─────── progress ────────────│
   │                             │                              │ (reads code)
   │                             │◀─────── progress ────────────│ (edits)
   │                             │                              │ (tests)
   │                             │◀─────── seeks_guidance ──────│ unsure!
   │◀───── "needs your call" ────│                              │
   │──── ratify / veto ─────────▶│── ratified/direct/veto ─────▶│
   │                             │                              │ (finishes)
   │                             │◀─────── result + evidence ───│
   │                             │  verify (gate + security +   │
   │                             │  human for judgment)         │
   │                             │  record to LEDGER            │
   │◀──────── "done: RATIFIED" ──│                              │
```

**Every step** is numbered in the Ledger; any step can be a `breach` (a trust
violation → protective layer → Steward).

---

## 4. Trust, but verify (the verification contract)

```
   the Agent says "done"
        │
        ▼
   ┌──────────────────────────────────────────────────────┐
   │  VERIFY — NEVER a bare "done"                        │
   │                                                      │
   │  1. correctness gate?   (deterministic: tests/curl/  │
   │      typecheck)         → VERIFIED_BY_GATE           │
   │  2. security clean?     (malware/injection/secret/   │
   │      veto-list)         → REJECTED_UNTRUSTED (block) │
   │  3. is it a JUDGMENT?   (refactor right? design OK?) │
   │        ├─ yes → to the STEWARD                       │
   │        │    · Steward accepts → RATIFIED             │
   │        │    · no gate at all → UNENDORSED (a human)  │
   │        │    · can't prove it → UNDECIDABLE (honest)  │
   │        └─ no  → pass through clean                   │
   └──────────────────────────────────────────────────────┘
```

**The rule:** the Constitution certifies only what it can *prove*
(deterministic gate + security clean + reproducible evidence). Everything that
is a *judgment* — and every security block — goes to a Steward. `UNENDORSED`
fails closed. It never certifies a lie.

---

## 5. The protective layer (bad actors, inside and out)

```
                          BAD ACTORS
   INSIDE:            │            OUTSIDE:
   jailbroken model   │            malicious task input
   poisoned plugin    │            prompt-injection
   poisoned corpus    │            malware / poisoned deps
   agent rewrote its  │            hostile harness
   own governance     │
        │                            │
        ▼                            ▼
   ┌───────────────────────────────────────────────┐
   │  THE GUARD (the protective layer)             │
   │  • veto-list (deny) · least-privilege         │
   │  • trust-taint on every input                 │
   │  • mechanical gates BELOW the model           │
   │  • the model CANNOT rewrite these             │
   │  • tamper-evident Ledger                      │
   └───────────────────┬───────────────────────────┘
                       │ any breach → Steward
                       ▼
                  REJECTED_UNTRUSTED (block)  or  RATIFIED (human clears)
```

**Why it's a layer, not a rule:** a jailbroken model or a poisoned agent can
rewrite a *rules file*; it cannot rewrite a *harness gate*. The Guard sits below
the model and enforces mechanically.

---

## 6. The learning loop (self-heal + self-learn, stewarded)

```
   ┌────────────────────────────────────────────────────┐
   │  run a job → record outcome to the LEDGER          │
   │     (cost, failed?, RATIFIED?, breach?)            │
   └───────────────────────┬────────────────────────────┘
                           ▼
   ┌────────────────────────────────────────────────────┐
   │  SELF-HEAL (deterministic — in the core)           │
   │  • timeout → retry · crash → resume from ledger    │
   │  • exactly-once · never silently lose a job        │
   └───────────────────────┬────────────────────────────┘
                           ▼
   ┌────────────────────────────────────────────────────┐
   │  SELF-LEARN (human-scaled — OUT of the core)        │
   │  • failures get a Steward post-mortem              │
   │  • successes get sampled Steward review            │
   │  • the override is the strongest lesson            │
   │  • a 'clerk' (not a judge) proposes Charter/template│
   │    changes; the Steward accepts or rejects         │
   └───────────────────────┬────────────────────────────┘
                           │ lesson (provenance-gated, inert until vetted)
                           ▼
                    the next run starts better
```

**The honest truth:** *self-heal* is real and in the core. *Self-learn* is real
but **human-scaled** — the Steward is the quality signal, and the loop can't
edit its own trust boundary. It never *silently* "gets better"; it improves
*with the Steward*.

---

## 7. The whole thing, one more time (the 30-second tour)

```
   STEWARD ──sets──▶ CHARTER ──(rules)──▶ CONSTITUTION
      ▲                                      │
      │ ratify/veto/direct                    │ gives a MANDATE
      │                              ┌────────▼────────┐
   GUIDANCE ◀── seeks_guidance ─────│  AGENT  does the │
   (a human answers)                │  work (Worker +  │
      │                             │  governance)     │
      │                             └────────┬────────┘
      │ every step lands in                 │ result + proof
      │ THE LEDGER ◀───────────────── VERIFY (gate/security/human)
      └── holds the whole thing in a COVENANT of trust, verified before trusted
```

---

## 8. What this design is NOT over-claiming (honest bounds)

- **Self-learn improves WITH the Steward** — never silently, never auto-trained
  on a weak signal alone.
- **Verification certifies only what is provable** — judgment is honestly marked
  `UNENDORSED` / routed to a Steward, never laundered into a machine "done."
- **The Guard is a gate, not a promise** — one layer of defense; it fails
  closed and escalates to a human; it does not pretend to catch everything.
- **The Covenant's messages are DESIGN, not frozen** — the next step is to
  finalize the wire contract and pass the conformance suite before it's a real
  covenant.

---

## Companion docs

- `spec/core-spec.md` — the covenant contract (the authoritative spec)
- `spec/covenant-vocab.md` — the vocabulary + keep-as-is rationale
- `docs/architecture/pm-summary.md` — the plain-english product summary
- `docs/architecture/vision-architecture.md` — vision + architecture
- `docs/design/core-under-attack.md` — the adversarial findings this rests on
- `docs/research/` — lessons from top harnesses