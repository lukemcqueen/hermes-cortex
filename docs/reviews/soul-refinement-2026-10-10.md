# SOUL.md candidate principle — 2026-10-10

**Status: PROPOSED — awaiting operator approval.** Identity documents are operator-owned;
this cron records the candidate rather than editing `~/.hermes/SOUL.md`.

## Evidence base

Today's sessions contained one recurring, expensive friction class: a cycle that was
correctly refused because its **task id under-described the diff**. Concretely, the
`pull-latest-hc-and-update` cycle carried a drift-reconciliation the update itself
demanded; the close was refused four times on scope-drift, held a 60-minute TTL wait, and
the *identical work* then closed CLEAN on the first attempt under a correctly-named cycle.
Adversarial-review data for the day: 151 reviews, technique distribution dominated by
`unverified-claim` (140), then `evaluation-awareness` (25), `scope-drift` (23).

## Candidate principle (local, Tier 3)

> ### 17. Name the Work for What It Is
>
> A governed change is judged against the name it was opened under. Open the cycle for the
> diff it will *contain*, not for the instruction that triggered it — a task id that
> under-describes the work fails on scope drift however good the evidence is. When a task
> grows a derived deliverable (a reconciliation, a recovery, a follow-on fix the task itself
> demanded), give it its own correctly-named cycle instead of folding it into the parent.
> Retire a mis-framed cycle through the state machine (`advance_task_state` → `cancelled`,
> reason logged) rather than forcing a close — never an override.

## Why it belongs in SOUL.md (not only a skill)

The skill (`change-checklist` Phase 0, `governance-lock-lifecycle` Pitfall 7) carries the
*procedure*. SOUL.md carries the *disposition*: the judgment that costs nothing to apply and
a lot to skip. The failure mode is not ignorance of the tool — it is opening a cycle in a
hurry under the instruction's own words. That is a character habit, which is what SOUL is
for.

## Merge note for the operator

If approved, add as a local subsection under `--- Local Principles ---` (below the canonical
12, generic to any agent, 4 sentences maximum as written above), then run
`python3 ~/hermes-cortex/ops/scripts/manage/soul-merge.py` and confirm the marker lands in
the deployed copy before committing. Keep it under the doctor's 15K WARN / 20K FAIL budget.
