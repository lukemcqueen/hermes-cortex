# SOUL.md candidate principle — 2026-10-11

**Status: PROPOSED — awaiting operator approval.** Identity documents are operator-owned;
this cron records the candidate rather than editing `~/.hermes/SOUL.md`.

## Evidence base

Today's sessions surfaced one *new* recurring friction class, distinct from
yesterday's (which was about naming the cycle). The class today was **the probe
built for a locked system run without the lock's precondition**:

- Two independent sessions (the morning task pass and the evening verification
  pass) each had their *first* `terminal` call — the one that gathers read-only
  state — **blocked by the governance enforcer** because it was a compound
  command or a bare `python3` invocation. Each session then re-routed the same
  reads through the already-lock-exempt MCP tools and got identical data. Nine
  `terminal` calls across the day's cron sessions failed this way.
- The evening pass put the diagnosis in its own report: *"the cron's prescribed
  `task-db.py` invocation is unreachable on this host as written — use
  `mcp__tasks__task_board` / `task_list` for reads (or the cron prompt needs its
  command updated to a lock-free form)."* That is the right disposition: notice
  the probe is wrong, name the working route, and flag the prompt for repair —
  rather than opening a lock to run a read.
- The same instinct appears twice more today, both times saving a cycle:
  (a) the briefing cycle's close was refused five times; the session stopped
  iterating and re-examined the *reviewer* as the probe, showing three of five
  findings false against ground truth, then escalated instead of correcting
  correct work; (b) an earlier pitfall already records that a failing check is
  more often a wrong detector than wrong code ("code was right 3x in one night").

The common disposition: **when a check fails, the failing thing is on trial
first.** Most candidates are not.

## Candidate principle (local, Tier 3)

> ### 17. The Failing Check Is on Trial First
>
> When a gate, probe, or reviewer refuses, treat the refusal as a claim to verify
> before treating it as a verdict about the work. Ask first what the check can
> actually see — a bounded diff cannot see files outside the repo, a write-class
> heuristic cannot tell a read from a write, a locked system must be read through
> its lock-exempt route. If the check is wrong, fix the check or route around it
> and prove the correction on the real path; escalate a structural mismatch
> rather than re-submitting the same correct work a fifth time.

## Honest scoping note — this OVERLAPS a canonical principle

Canonical **Principle 11** already carries *"Question the probe before declaring
a bug — a failing test can be testing the wrong thing. When a check fails, first
verify the probe's own assumptions, then the schema."* The candidate above is
the same disposition applied to the *enforcement* gate and the *adversarial
reviewer* rather than to a unit test.

So the operator has three defensible choices, in my order of preference:

1. **Widen Principle 11 by one sentence** (cheapest, no new local principle, no
   budget growth) — add to the existing bold sub-point: *"...the same applies to
   a gate or a reviewer: a bounded diff cannot see outside its repo, and a
   write-class heuristic cannot tell a read from a write."*
2. **Adopt as local principle 17** exactly as written above, if the operator
   judges the enforcement/reviewer case distinct enough to name.
3. **Reject** — if Principle 11 is judged sufficient and today's instances are
   covered by it. That is a legitimate outcome; the evidence base is recorded
   either way.

I did not resolve this in favor of my own first draft. Flagging it is the point
of the report.

## Why it belongs in SOUL.md (not only a skill)

The *procedures* live in skills (`survey-before-action`, `governance-lock-lifecycle`,
`adversarial-review-passoff`). SOUL.md carries the *disposition*: the reflex that
costs nothing to apply and a lot to skip. The failure mode is not ignorance of a
tool — it is treating a red gate as ground truth and bending good work to satisfy
a bad measurement. That is a character habit, which is what SOUL is for.

## Suggested placement

Add under the local-principles block (below canonical 12), generic to any agent,
six sentences as written above, then run
`python3 ~/hermes-cortex/ops/scripts/manage/soul-merge.py` and confirm the marker
lands in the deployed copy before committing. Deployed SOUL is currently 13,408
bytes against the doctor's 15K WARN / 20K FAIL budget — there is ~1.5K of room,
so this lands at WARN, not FAIL.

## Local Principle 16 candidate — note from the evening pass (secondary)

The evening pass's own note asks that the cron's prescribed command be made
lock-free. That is a prompt-repair item, not an identity item; recorded here so
it is not lost, and filed with the orchestrator as the route fix.
