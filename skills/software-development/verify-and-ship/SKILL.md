---
name: verify-and-ship
version: 0.1.0
category: software-development
description: >-
  Pre-ship verification: the mandatory change checklist and the eight-question
  self-critique before end_change() or delivery (absorbed change-checklist +
  reflexion-check). Load before ANY delivery or close.
pinned: true
aliases:
  - change-checklist
  - reflexion-check
related_skills:
  - task-orient
  - execute-right
  - loop-governance
  - governance-closeout
---

# Verify and Ship — Pre-Delivery Validation

The easy path (one file, one test) is never the complete path. Ask: what else
does this touch? Did the SYMPTOM resolve? Did I check siblings? Did I run the
doctor? Did I push so the fleet benefits? Run the self-critique BEFORE
delivering anything; run the checklist before any end_change().

## The eight reflexion questions

1. **Did I complete everything the user asked?** Re-read the original request,
   including implicit items. If NO: finish before delivering.
2. **Did I verify every claim with real tool output?** "It should work" is not
   verification; "curl returned 200" is. A claim that a suite passes is a claim
   about a RUN — commit the run. A claim about a guard is verified AT the
   guard, never inferred from the caller. Name the BUILD, not just the run (a
   demo of `target/release/<bin>` measures the last build, not the source).
   A runner missing here is solved by installing it into an isolated venv, not
   by softening the claim; only if it genuinely cannot run HERE, verify the
   substance another way and LABEL which route you used. Cite evidence the
   reader can REACH (a path they can open).
3. **Did I follow governance for every change?** Every file created/modified:
   begin_change → work → feedback_accept → end_change, scored, no orphans. If
   NO: score the missing cycle or confess the gap.
4. **Did I handle all edge cases and failure paths?** Error path, empty state,
   malformed input, sibling call sites. Probe the GATE itself: point the
   checker at input it must reject and show it failing non-zero. A failure is
   only a finding once you know the check RAN (run it with the runner it was
   written for). Probe the PROBE: when a check fails, verify its own
   assumptions before blaming the artifact.
5. **Anything I would do differently?** Document it; if recurring, save as a
   lesson.
6. **Irony check:** does my execution contradict my change? (shipping a
   "be thorough" rule without running the verifier on it). If so: undo the
   bypass, do the rule, then ship.
7. **Anti-sycophancy:** did I push back when I should have? Silence with a bad
   idea is a trust violation. If overridden, note the override and execute
   faithfully.
8. **Visibility:** did the operator see progress during a long run? Send a
   short progress line at each phase boundary of anything lasting minutes.

Score: HIGH (all 8 pass) / MEDIUM (minor gaps, flag them) / LOW (fix before
delivering) / ZERO (cannot verify core claims — investigate, do not deliver).

## Change checklist (before end_change)

**Phase 0 — survey the surface (before begin_change):**
- Pushback check: wrong/harmful/better-alternative? Object BEFORE begin_change;
  silence is not consent. Override is final; execute faithfully.
- **Plan review before building (operator standing rule)** — non-trivial
  builds get the PLAN pro-reviewed FIRST via
  `ops/scripts/orch-bus/adversarial-review.py --cycle-id <id> --review`. Pass
  the material TEXT (content, not a path); read the stored row back — a CLEAN
  verdict validates CLAIMS, never predicted consequences (the RED run is what
  falsifies those). Never phrase the material as a REQUEST (filed as
  injection); include the code map, hard constraints, rejected options.
- Name the cycle for the diff it will CONTAIN, not the instruction that started
  it; sized so the close review can read it (blob count, not line count).
- grep the repo for the old name/term; check cron jobs.json; cron install
  arrays; updater register() calls; doctor expected-cron lists; deployed path.
- PII scan — `secret-leak-detector.sh` before pushing.

**Phase 1 — test the change (no simulated output):**
- Scripts run with real inputs; DOGFOOD: the deployed copy runs its real
  invocation. Syntax: .sh bash -n; .py py_compile; .yaml safe_load.
- A scripted bulk edit must ASSERT its match count, then be scanned for
  artefacts (escaping residue, duplicates, self-contradicting never-clauses).
- Run the SIBLING tests that exercise the seams you changed; prove
  pre-existence of a failure at the range base in a worktree (run both sides
  the same way, absolute paths).
- Changing a DEFAULT CONSTANT breaks hardcoded old literals in tests — sweep
  both shapes (fixture AND assertion), run to prove both moved.

**Phase 1.5 — adversarial verification (mandatory, no bypass):**
- Static gate per changed script: `adversarial-verify.py --file <f> --level
  A2 --gate`; A4 for plugins/, hooks/, mcp-servers/, ops/scripts/manage/,
  cortex_doctor/, enforcer, tests. Critical/high → block. No --no-verify.
- Pin before/after comparisons to an immutable revision (the RANGE BASE —
  `git merge-base origin/main HEAD`), name both shas in the artifact; assert
  the baseline reproduces the defect or the comparison proves nothing.
- A captured check transcript carries its EXIT CODE and WARNING COUNT.
- Evidence scripts are READ-ONLY — never repair what they measure; never
  commit a query's output before seeing it return rows.
- A test judged by the close reviewer DERIVES expected values from the
  system's own surface (never a hand-copied constant-equals-constant echo, a
  magic bound, or a message substring).
- Commit the EVIDENCE artifact BEFORE you close — a load-bearing claim that
  lives only in the close note is filed unverified-claim and refuses the
  close. Run the checks, capture real output (command + its own rc, measured
  unpiped) into `docs/evidence/`, commit it in the SAME cycle.
- ONE note, ONE run — every number in the close note must come from the SAME
  run as the committed artifact beside it.

**Phase 2 — multi-OS:** hardcoded paths → portability helpers; systemctl vs
launchctl vs brew by host.
**Phase 3 — multi-role:** hook/enforcer changes tested in a throwaway repo;
role matrix (Titus/Joseph/Esther/Kustos) — verify none broken.
**Phase 4 — docs:** never document a command you have not executed; new script
→ register in cortex-update.sh; new auto-loaded skill → manifest; agent
workflow change → AGENTS.md/SOUL.md.
**Phase 5 — final verification:**
- No dangling leftovers — DECIDE: land it, or state a decision backed by a
  measurement. Never land a peer's in-flight edits.
- Symptom proof — the specific error/alert/blocker is gone, not just "compiles".
- Stale expected-lists cleaned (removed crons also removed from uninstall arrays).
- Doctor clean — `cortex-doctor.py --quiet`; record its EXIT CODE and warning
  count, not just the ✅ lines. Warnings and info are not a licence to move on:
  fix or dispose (`--disposition ... --as deferred|deliberate`), BATCHED and
  LAST, after the push.
- Deploy, THEN push — that order, nothing committed in between (deploy-map
  files must match deployed tree). Run the doctor after deploy.
- Verify the landing: `verify-landed.py --repo . --base <previous tip>`
  (receipt + deploy-map copies + origin equals tip).
- Pushed — `git log --oneline -1 origin/main` shows your commit; load
  `shared-repo-push-gates` BEFORE the first push attempt.
- Gate scoping: a host-wide gate whose remedy requires a Hermes session stays
  repo-scoped; widen only when any user's remedy exists.

**Phase 6 — reflexion:** run the eight questions; LOW/ZERO → fix before
delivering. Ask: "What is the most likely thing I got wrong?"

## Anti-patterns

"I tested it manually" · "agents won't see that message" · "the rest is
trivial" · "docs later" · "the hook didn't catch it" · "I'll write a migration
script" (the commit IS the migration) · "worked from my repo terminal" (test
from the deployed path).
