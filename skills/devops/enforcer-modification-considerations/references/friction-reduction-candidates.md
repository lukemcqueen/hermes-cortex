# Enforcement friction: taxonomy, candidates, and what must NOT change

## When to Use

- You are about to change the write-classifier, a gate's timing, or a close/push requirement.
- Enforcement friction is being reported as "wasted cycles" and you need to know which friction is
  load-bearing before you relax anything.

Every rule here comes from the block messages the gates emit plus counted log evidence — not from
reading the enforcer's intent.

## Measure first (lock-free)

- `search_files(pattern="GOVERNANCE LOCK REQUIRED", path=~/.hermes/logs, output_mode='count')` gives
  per-file counts; do the same for the skills-gate and TDD-gate texts.
- The same event is written to `agent.log*` AND `errors.log*` — halve the total before quoting it.
- Cycle overhead is visible in `cycle_query`: a pre-commit hook cycle per commit, and a lock-carrier
  `push-*` cycle per publish.

## The root cause is TIMING, not strictness

Enforcement acts at the WRITE, while the information needed to satisfy it arrives LATE: skills-credit
staleness is discovered at the first write, the TDD requirement at commit, scope drift at close, the
publish lock at push, a stranded session at the NEXT `begin_change`. A fix that moves a signal
earlier therefore buys as much as one that relaxes a rule — and costs no security.

## Candidates, in priority order

1. **Publish on the receipt, not on a lock.** The push gate demands an active lock AND (for an
   always-review range) a CLEAN receipt, but the close releases the lock — so every publish costs a
   throwaway cycle. The receipt is the STRONGER artifact: bound to the range and to content blobs.
   Two places must change: the hook's own lock check (`ops/scripts/pre-push-pull`) and the enforcer's
   lock path, which blocks `git push` before the hook ever runs. Gate the carve-out ON the receipt —
   never unconditional, or `--no-verify` becomes an unreviewed push.
2. **A rename tool for an OPEN cycle.** Scope drift is diagnosed by comparing the task id with the
   changed files; today the remedies are re-wording the note (does nothing) or a cancel plus TTL wait.
   `reframe_change(new_task_id, reason)`, logged to `task_events`, fixes it in one call. Bootstrap
   wrinkle: it cannot be used on the cycle that builds it.
3. **Warning-first scope pre-flight.** Before the review, report the changed paths against the task
   id and point at the rename tool. Warn, never block — the reviewer keeps its authority.
4. **Cosmetic tokens must not make a read write-class.** Recurse into `$()`/backticks (a substitution
   of read primitives is a read); add stdout-only builtins (`echo`, `printf`, `true`, `sleep`) to the
   read set; treat `2>/dev/null`/`2>&1` as non-writing. Keep `>`, `>>`, `tee`, `find -exec`, `sed -i`
   write-class. Then print the CORRECTED command on a cosmetic-only block, so a wasted call becomes a
   one-line lesson instead of a retry loop.
5. **Signal staleness where work starts, not where it is refused.** Report stale always-section
   skills at `begin_change`/`check_lock`. The same skills stay required — the agent just learns
   before its first write instead of losing it. Content-hashed credit stays exactly as strict.
6. **Tell the reviewer what it cannot see.** The close gate renders a BOUNDED window of the range
   diff, so a complete evidence file can be filed as "unverified claim" — indistinguishable from
   fabrication. State the range size and which files were elided, and separate "not visible in my
   window" (info, non-blocking) from "claim contradicted" (blocking). Pass prior findings and require
   resolved/unresolved per finding so a fixed one cannot be re-filed as new.
7. **Cheap cleanups.** Pre-commit hook cycles belong in `unscored_reason` rows, not scored ones with
   LOOP decisions nobody acts on. `check_lock` and `begin_change` must read ONE store (today they
   legitimately disagree). A refusal should print `expires_at` and the legitimate exits. The TDD
   requirement should be announced at `begin_change`.

## Do NOT change

- The lock requirement for unreviewed mutation. Every candidate above either moves WHEN the
  requirement is learned, or swaps a weaker artifact (a lock) for a stronger one (a range-bound
  receipt).
- Content-hashed skill credit; the reviewer's power to block MEDIUM+ findings; the logging and
  budget on `--no-verify`/`force`; the requirement that a push's exact range be reviewed.
- A check that CANNOT RUN stays a third outcome (exit 3 / could-not-verify). Turning "cannot verify"
  into "allow" is a security regression wearing friction relief as a disguise.
