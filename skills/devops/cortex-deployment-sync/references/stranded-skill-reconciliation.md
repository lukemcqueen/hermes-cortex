# Reconciling stranded deployed-only skills

Topical depth for `cortex-deployment-sync` → "When the update reports stranded
deployed-only skills". `ops/scripts/manage/reconcile-stranded-skills.py` is the tool;
this is how to run it, how to judge what it reports, and the traps that cost time.

## What "stranded" means

A deployed skill file whose content appears in NEITHER the repo working tree NOR any
committed revision. Direction is decided by content, so a fresh clone cannot hide it
and mtime is irrelevant. The detector owns that definition — take the stranded list
from `check-skill-drift-parity.py` rather than re-deriving it, so a second, looser
implementation cannot disagree with the gate.

## Classification, and why a rewrite is never auto-applied

| Deployed vs repo | Meaning | Action |
|---|---|---|
| pure superset (dropped == 0) | the fleet's newer text | copy (`--apply`) |
| drops lines too | a REWRITE — may have lost a lesson | read every dropped line, decide, merge by hand |
| no repo counterpart | file only exists deploy-side | copy whole file |

A tool that overwrites on a rewrite silently deletes whatever the deployed copy
dropped. Report-by-default is the safe shape: the human/agent decision is the point,
and the printed DROP lines are the input to it.

Judging a drop: a fragment of a sentence the same section rewrites in place is
superseded (take the deployed side); a whole bullet or lesson that is ABSENT
deploy-side means the deployed copy lost it — keep the repo side and merge the
additions by hand. Verify "still carries the topic" with marker counts rather than by
feel (`grep -ci` for the distinctive terms in the deployed copy).

## Reproducing a BEFORE state re-runnably

An artifact that claims "the detector reported N stranded before the fix" is a claim
the reviewer cannot check once the fix has landed — the state is gone. Reproduce it:

```bash
git worktree add /tmp/pre-reconcile <commit-before-the-fix>
python3 /tmp/pre-reconcile/ops/scripts/manage/check-skill-drift-parity.py
# run the copy FROM the worktree: a tool that resolves its root from its own path
# (Path(__file__).resolve().parents[3]) then measures THAT tree
git worktree remove --force /tmp/pre-reconcile && git worktree prune
```

This generalises: any tool that derives its root from `__file__` can be pointed at an
old revision by running its old copy, which is stronger than `git show <sha>:<path>`
into a temp tree (that variant has no `.git`, so checks that consult committed
revisions change behaviour). Authenticity then comes from the commit being measured,
not from a label in the text.

## Pitfalls that cost time here

- **Resolve a relative argument path BEFORE a subprocess changes cwd.** A tool that
  runs a helper with `cwd=<repo>` and passes a relative `--script`/`--config` path has
  it resolved inside that repo, so the helper is "missing" and the tool reports
  could-not-verify — masking the real cause as a clean-looking refusal. `Path(arg).resolve()`
  at parse time.
- **A new production script must ship its test in the SAME commit** — the pre-commit
  TDD gate blocks otherwise (`TDD IRON LAW VIOLATION — new production code without a
  test`). Write the test in the same commit, not as a follow-up.
- **Give the tool an injectable input seam so the test drives it with CONTROLLED
  state.** Driving it against the live skill trees makes the verdict depend on whatever
  the host happens to look like; a `--drift-script`/`--repo`/`--deployed` seam lets the
  test build throwaway trees and a stub detector, and it is the only way to exercise
  the failure branch — construct a detector that exits non-zero and assert the
  could-not-verify outcome and message.
- **Test the fixture's model of the paths, not just the logic.** A fixture that puts
  deployed files under an extra `skills/` level makes every case report "missing" and
  the suite passes for the wrong reason. Assert the copy actually happened (read the
  file back), not merely the exit code.
- **Size evidence artifacts for the close gate's review window.** It budgets a bounded
  amount of diff across the whole range and omits the middle, so one large artifact
  reaches the reviewer truncated and its claims read as unevidenced. Keep each artifact
  to a few hundred bytes–2 KB, put the load-bearing command and its `rc=` FIRST, and
  split rather than grow.
- **Stranded always-section skills cause stale skill credit** (see SKILL.md); fixing
  the drift is the durable fix, re-loading skills each session is the workaround.
