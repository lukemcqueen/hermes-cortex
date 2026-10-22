# Publishing a reviewed range

## When to Use

- You have a committed, reviewed range and need it on `origin/main`.
- A push was refused for a missing lock or a missing review receipt.
- You are about to conclude the push gate is broken because a just-closed cycle did not make the
  push possible — the publish flow below is the sequence that satisfies all of the gates.

Getting a commit set from your local branch onto `origin/main` in a governance-enforced repo:
the gates in the order they fire, what each one wants, and the recipe that satisfies all of them.

## The gates, in the order they hit

1. **Enforcer (tool level).** `git push` is write-class, so it needs an ACTIVE governance lock.
   Without one the call is refused and the hook never runs.
2. **Pre-push hook (`ops/scripts/pre-push-pull`).** Runs only if the lock gate passed. Verifies
   `core.hooksPath` points at `~/.hermes-cortex/hooks`, requires an active lock file, and — only
   when the range touches an always-review path — requires a CLEAN review receipt covering that
   range. The same path also runs the update/deploy, the doctor and the landing verification.
3. **Remote.** A non-fast-forward push is rejected only after all of the above passed.

## Is a receipt required for this range?

Read `ops/scripts/lib/always-review-paths.txt` — that list is the authority. Hardcoding paths from
memory drifts the moment the list changes. If nothing in the range matches, the push needs the lock
only, and it can go out immediately after the owning change closes.

## The receipt is bound to CONTENT, not to the tip

A receipt records `reviewed_blobs` (path → blob sha) for the range it reviewed, and the gate accepts
it when those blobs COVER every blob the pushed range changes. Two consequences worth knowing before
you conclude the gate is broken:

- A **rebase** that rewrites the tip of byte-identical content does NOT invalidate the receipt.
  A tip-equality rule breaks on any shared checkout; content coverage is why it no longer does.
- A **new commit landing inside the range** DOES invalidate it — that content is genuinely
  unreviewed. Do not widen the rule to make it pass; keep the deploy+push window quiet instead.

## Recipe

```text
# 1. Let the owning change CLOSE first — its close writes the receipt for the range.
feedback_accept(cycle_id=<owning>, task_id="<owning>", note="...")
end_change(task_id="<owning>")                     # lock released, receipt written

# 2. Open the short publish cycle. THIS is the lock the push gate needs.
begin_change(task_id="push-<change>",
             description="Hold the lock the push gate requires; no content change")

# 3. Deploy, then push, then verify from ORIGIN (never from your own branch).
bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force     # deploy is the LAST step; nothing committed after it
git push origin main
git fetch origin --quiet
git log --oneline -1 origin/main                            # shows your commit
git rev-list --left-right --count origin/main...HEAD        # want '0 0'

# 4. Close the publish cycle, with the push output as its evidence.
feedback_accept(cycle_id=<new>, task_id="push-<change>", note="<push output + landed tip + '0 0'>")
end_change(task_id="push-<change>")
```

Independent confirmation of the landing (do not substitute "the branch looks clean"):

```text
python3 ops/scripts/manage/verify-landed.py --repo . --base <previous tip>
# exit 0 all checks hold · 1 a real mismatch, named · 2 COULD NOT VERIFY — a partial check is not a pass
```

## Pitfalls

- **Your OWN open cycle is what the doctor reports as a failure, and that collides with the carrier-cycle
recipe above.** While any cycle is PENDING, `cortex-doctor` prints `❌ PENDING cycles` and its overall
line FAILS, so `cortex-dogfood.sh` ends "DOGFOOD FAILED" even though the deploy it performs has already
run, and the pre-push hook refuses with "Push blocked: doctor reports 1 failure". A clean doctor and a
held lock are therefore mutually exclusive: sequence it so the lock is GONE before the push, and let the
receipt carry the push (the enforcer's push-receipt carve-out authorises a lock-free push when a CLEAN
receipt covers the range — it has done so for real ranges). If a lock-free push is then refused with
`GOVERNANCE LOCK REQUIRED` while the receipt exists on disk, do NOT thrash and do not reach for an
override: opening a carrier cycle re-creates the doctor failure, so the two refusals together are a gate
interaction to diagnose (start with the carve-out in the enforcer and the receipt's blob coverage) and to
report, not something to force through.
- **Deploy is the LAST content step.** Any commit made after the deploy leaves the deployed tree
trailing HEAD, which fails the `Deploy sync` check and blocks the push. Deploy, then push, with
nothing committed in between.
- **Never `--no-verify` a push.** The hook is the layer that demands the receipt; skipping it
publishes unreviewed content and the bypass is logged and budgeted.
- **An empty range proves nothing.** Once the push lands, `origin/main..HEAD` is `0 0`, so a cycle
opened afterwards has nothing to review and will close without having reviewed anything. Verify
against the commit you actually pushed, not against "the branch is clean".
- **A peer's unrelated commit is not your blocker.** Deploy-sync and the receipt are both scoped to
what the range CHANGES, so a peer's docs-only commit no longer blocks a push whose own deploy-map
files are deployed. A peer commit that touches a deploy-mapped file still does — correctly.
