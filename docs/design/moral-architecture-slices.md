# Moral Architecture — Story/Slice Build Plan (Hermes Cortex)

> **Status:** DESIGN (build plan) — the fine-grained, deepseek-flash-sized task
> list a weak model can execute without drifting.
> **Pairs with:** `docs/design/moral-architecture-adaptation.md` (the analysis
> these slices implement) · `docs/reference/moral-architecture/README.md` (the
> source digest).
>
> **Why this doc:** the adaptation doc names **nine** architecture changes. A
> weak model handed "make the failure-propensity register machine-readable"
> will drift. Each task here is **one file (or one tightly-coupled pair) + one
> test + one RED→GREEN cycle**, named by exact path, with the exact assertion.
> A task is done when its test passes against the real pipeline — never before.

---

## The discipline (non-negotiable for the weak model)

1. **TDD Iron Law:** write the failing test FIRST, watch it fail (RED) for the
   right reason, then minimal code (GREEN). No production code before a failing
   test.
2. **One file per task** unless two files are inseparable (schema + its
   validating script).
3. **Done = the owning test green** against the real pipeline, full suite still
   green.
4. **`BUILD`** = mechanical shape/wiring (weak model OK). **`CHECK`** = a
   security guarantee (a conformance test, or a fail-closed gate) — a strong
   model writes **and** verifies. **Stop before each CHECK, commit the
   accumulated BUILD work, hand to the strong model.**
5. **Governance for every change** — `begin_change` → work → `feedback_accept` →
   `end_change`. Never `SKIP_SCORE=1`, never `--no-verify`.

### Story order (strictly top-to-bottom)

```
Story M1  failure-propensity register (goring ox)          ← highest leverage, lowest cost
Story M2  layer-tag the guardrail registry (placement rule)
Story M3  refusal log + metrics (Balaam's donkey)
Story M4  seam ownership (named owners)
Story M5  permission TTL / Jubilee (expiry by default)
Story M6  independent evaluator + named human (evaluator independence)
Story M7  unannounced evaluation / honeypot (defeat device)
Story M8  evidence-command allowlist at end_change (honest weights)  ← enforcement; strong model only
```

Stories M1–M3 are the `BUILD`-heavy mechanical work. M4–M8 are mostly
documentation or enforcement changes with thin test surfaces — they still get
sliced, but several are `CHECK` (fail-closed) and several are pure-doc `BUILD`.

---

## Story M1 — Failure-propensity register (goring ox, Ex 21:28–29)

> Once a propensity is documented, deploying without a restraint is the culpable
> act, and the logs prove notice.

**M1.1 — Add `restraint` + `noticed` fields to the register schema** — BUILD
- File: `docs/guardrail-registry.json` (add two fields to every class) + a new
  `ops/scripts/manage/check-restraint-registry.py` that loads the JSON and
  validates every class has a non-empty `restraint` and a valid ISO `noticed`.
- Test: `python3 ops/scripts/manage/check-restraint-registry.py` exits 0 on a
  well-formed registry, non-zero + names the class if `restraint` is empty.
- Depends: nothing (the registry already exists).

**M1.2 — Doctor check: every known failure mode has its restraint present** — CHECK
- File: `cortex_doctor/checks.py` (new check) — for each class in
  `guardrail-registry.json`, confirm the `restraint` names an artifact that
  actually exists on disk (a `doctor:` check, a `hook:`, a `skill:`, an
  `enforcer:`).
- Test: a fixture registry with one class pointing at a nonexistent restraint →
  doctor reports a FAIL for that class; all-restraints-present → PASS.
- Depends: M1.1.

**M1.3 — `restraint` on the existing `known_gaps` list** — BUILD
- File: `docs/guardrail-registry.json` (`known_gaps` array) — convert each prose
  gap into an object `{class, restraint, noticed}` so the doctor check in M1.2
  covers known gaps too.
- Test: `check-restraint-registry.py` validates `known_gaps` (reuse M1.1's
  validator; extend it to also walk `known_gaps`).
- Depends: M1.1.

---

## Story M2 — Layer-tag the guardrail registry (placement rule)

> A requirement enforced *only* in the model is not enforced — it is encouraged.
> Tag every class so a scan can answer "enforced or just hoped?"

**M2.1 — Add `layer` + `tier` fields to every class** — BUILD
- File: `docs/guardrail-registry.json` — add `layer` (`model`|`harness`|`ops`|
  `institutional`) and `tier` (`enforced`|`encouraged`|`detected`) to every class.
  Assign honestly: a class whose only artifact is a `SOUL.md:…` reference is
  `encouraged`, not `enforced`.
- Test: `check-restraint-registry.py` (extended) rejects any class missing
  `layer`/`tier`, and rejects a class tagged `enforced` whose artifacts are
  all `SOUL.md:`/`AGENTS.md:`/`skill:` references (a `model`-layer artifact can
  never be `enforced`).
- Depends: M1.1.

**M2.2 — "encouraged-not-enforced" gap report** — CHECK
- File: `ops/scripts/manage/check-restraint-registry.py` (extend) — emit a report
  listing every class tagged `tier: encouraged` where `layer: harness` *could*
  express it (i.e. a human-marked `should_be_enforced: true` field is present),
  so the drift is surfaced rather than silent.
- Test: a fixture with one `should_be_enforced: true` + `tier: encouraged` →
  script exits non-zero naming it.
- Depends: M2.1.

---

## Story M3 — Refusal log + separate metrics (Balaam's donkey, Num 22)

> Track refusal precision/recall *separately from* task satisfaction, or a
> single metric breeds the refusal out.

**M3.1 — Refusal log schema + writer** — BUILD
- File: `ops/scripts/manage/refusal-log.py` (new) — append a JSONL record
  `{ts, session_id, context, challenged: bool, override_outcome: (upheld|overridden|none)}`
  to `~/.hermes-cortex/data/refusals.jsonl`. `challenged=false` = the agent did
  not push back (baseline); `challenged=true` = pushback happened, with outcome.
- Test: call `refusal-log.py record --challenged --outcome overridden` → a line
  appears in the JSONL with the right shape (parse it back).
- Depends: nothing.

**M3.2 — Refusal metrics report (precision / recall / false-refusal)** — CHECK
- File: `ops/scripts/manage/refusal-log.py` (add `report` subcommand) — over the
  JSONL, compute: refusal rate, false-refusal rate (challenges that were
  overridden = wrong), override rate. **Do not fold into one number** — print the
  three lines separately.
- Test: a fixture JSONL with known counts → `report` prints the three
  hand-computed numbers exactly.
- Depends: M3.1.

---

## Story M4 — Seam ownership (named owners)

> Seams are where accountability disappears. Name a single owner per seam.

**M4.1 — Name Seam A and Seam B owners** — BUILD (doc-only)
- File: `docs/agent-architecture.md` — add a short "Seam ownership" section:
  Seam A (model↔harness: prompt-injection / untrusted-content boundary) owned by
  the enforcer + security-notice marker; Seam B (harness↔controller: MCP
  arg-passing, tool gating) owned by the loop-governance MCP + enforcer. One
  named owner per seam, stated explicitly.
- Test: none (doc) — but grep the doc for "Seam A" and "Seam B" with a non-empty
  owner in the same line.
- Depends: nothing.

---

## Story M5 — Permission TTL / Jubilee (Lev 25)

> Power expires by default; affirmative re-grant is the control.

**M5.1 — Bus permission expiry field + re-grant sweep** — BUILD
- File: extend the bus permission schema (see `core/cortex_bus/schema/auth.sql`)
  with an `expires_at` column, and add
  `ops/scripts/manage/bus-grant-sweep.py` that lists grants past `expires_at`.
- Test: seed a grant with `expires_at` in the past → the sweep lists it; a
  future grant is omitted.
- Depends: nothing (bus schema is in `core/cortex_bus/`).

**M5.2 — Doctor check: no indefinite grants without a named decision** — CHECK
- File: `cortex_doctor/checks.py` — warn if any bus grant has `expires_at IS NULL`
  AND no "indefinite" justifier field is set.
- Test: fixture with an indefinite grant lacking a justifier → doctor WARNS.
- Depends: M5.1.

---

## Story M6 — Independent evaluator + named accountable human

> The evaluator must not report to the evaluated (§8.7 rule 1).

**M6.1 — Maker/checker split as an enforced, not recommended, rule** — BUILD (doc)
- File: `docs/architecture.md` (or `docs/agent-architecture.md`) — state that the
  adversarial-verifier, for quality-critical work, MUST run on a **different
  model and different context** than the implementer, and name the mechanism
  (a second session / orchestrator-owned review) rather than a same-session
  self-check.
- Test: none (doc).
- Depends: nothing.

**M6.2 — Named accountable human per autonomous cron** — BUILD
- File: `docs/fleet-reference.md` cron table — add an "Accountable" column
  (a named operator) to every autonomous cron row; note "takeover latency"
  is a measured metric, not an assertion, for irreversible crons.
- Test: none (doc).
- Depends: nothing.

---

## Story M7 — Unannounced evaluation / honeypot (defeat device)

> Assume evaluation-awareness; test unannounced, in production conditions.

**M7.1 — Honeypot probe cron (orchestrator-owned)** — BUILD
- File: `ops/scripts/agent/agent-unannounced-probe.py` (new) + register in
  `ops/scripts/install-crons.sh` — schedules a low-frequency probe that injects
  a honeypot task (a bus message or artifact) a non-vigilant agent would
  mishandle, and records the delta between believed-test and believed-deployment
  behavior.
- Test: the script accepts a `--dry-run` flag that emits the probe payload and a
  `--report` that reads back the recorded loop; both exit 0 on a clean run.
- Depends: nothing.
- *(This is a thin slice — the actual honeypot content is a follow-up that the
  orchestrator authors, not the weak model.)*

---

## Story M8 — Evidence-command allowlist at end_change (honest weights)

> `end_change` must refuse a `feedback_accept` that cites "verified" without a
> real evidence command — the report's "verify the conduct, not the profession."

**M8.1 — EvIDENCE_COMMANDS allowlist + end_change gate** — CHECK (enforcement)
- File: extend the loop-governance MCP (`mcp-servers/loop-gov-mcp.py`) so that
  `feedback_accept` with a note claiming `verified:`/`tested` but citing no
  command from the EVIDENCE_COMMANDS allowlist (a test run, a grep, a compiled
  output) fails closed with "evidence required" — or the note is accepted only
  when it names a real prior tool output.
- Test: `feedback_accept` with a bare "verified: works" note → refused; with a
  note naming `cargo test` output → accepted.
- Depends: nothing (enforcement).
- ⚠️ **Orchestrator-only + strong model.** This touches the enforcement chain —
  do NOT hand to a weak model; it is listed for completeness and must be gated
  behind the `enforcement-change-safety` and `enforcer-modification-considerations`
  skills.

---

## Where we are

| Story | Tasks | Kind | Status |
|-------|-------|------|--------|
| M1 failure-propensity register | M1.1–M1.3 | BUILD/BUILD+CHECK | 🔲 not started |
| M2 layer-tag registry | M2.1–M2.2 | BUILD/CHECK | 🔲 not started |
| M3 refusal log + metrics | M3.1–M3.2 | BUILD/CHECK | 🔲 not started |
| M4 seam ownership | M4.1 | BUILD (doc) | 🔲 not started |
| M5 permission TTL | M5.1–M5.2 | BUILD/CHECK | 🔲 not started |
| M6 independent evaluator + named human | M6.1–M6.2 | BUILD (doc) | 🔲 not started |
| M7 unannounced probe | M7.1 | BUILD | 🔲 not started |
| M8 evidence allowlist | M8.1 | CHECK (enforcement) | 🔲 not started |

**Read order for the implementer:** M1 → M2 → M3 are the BUILD-heavy, mechanical
wins with real test surfaces — start there. M4/M6 are pure doc `BUILD`s. M5/M7
are script `BUILD`s with thin `CHECK`s. M8 is enforcement and last.