# Adversarial-review cost reduction — plan

**Status: PLAN ONLY. Nothing here is implemented.** Cycle: `adversarial-review-cost-plan`
(12792). Operator: Luke, 2026-10-18. Scope agreed: levers **A + B + C**.

## 1. The problem, measured

Four read-only questions to one agent (00:08–01:35 KST, 2026-10-18) cost **6 governance cycles.
Every one of them either refused or returned nothing: six calls hit the 300 s ceiling with no verdict
at all, two closes were refused on findings, and two sessions had to be force-cleared by the
operator.** Five of the six cycles were closes on documentation-only commits.

> **Cycle accounting corrected 2026-10-18** (reviewer finding on this document: §1 listed 3 cycles
> while §2 referenced a later one, so the totals did not reconcile). The table below is the complete
> set; 12792/12795/12797 are the later ones §2 referred to.

| Cycle | What it was | Result |
|---|---|---|
| 12777 | read-only fan/temp sampling, empty diff | refused — "prose-only claim"; remedy: commit the transcript |
| 12779 | 79-line evidence transcript, 1 file | refused — 3 findings, **all on a peer's commit** |
| 12782 | re-close of the same 79-line artifact | **3 × 300 s timeouts, no verdict**, lock stranded |
| 12792 | 3-file docs plan, 153 lines, no code | 300 s timeout, no verdict (later re-reviewed: FINDINGS) |
| 12795 | 1-file docs commit, 41 lines | 300 s timeout, no verdict |
| 12797 | 1-file docs commit, 52 lines | 300 s timeout, no verdict |

Verdicts and timeouts both traced to one thing: **the close reviewed a window that was
two-thirds someone else's work.** The refused range was 11 files / 448 lines across three
sessions (soul-refinement cron, a stalled-rebase session, and mine at 79 lines).

**Provenance of the citations below** (reviewer finding on this document, 2026-10-18): every
`file:line` reference in §2, §3 and §5 was read from `mcp-servers/loop-gov-mcp.py` and
`ops/scripts/manage/review-material.py` at the revision current when this was written, but the
citations themselves are NOT part of this document's diff and are therefore UNVERIFIED in it — the
line numbers may drift as the file changes. Treat them as a map, and re-grep before relying on a
line number. The plan's claims about behaviour are separately pinned by the tests it names.

## 2. Root cause (code, not opinion)

The audit already separates authorship — but only for **presentation**, not for **scope**.

`mcp-servers/loop-gov-mcp.py`:

- **5395–5398** — `_base = git rev-list -1 --before=<lock.started_at> HEAD`: the review window
  is *lock-start → HEAD*, so any peer commit landing while my lock is held enters my review.
- **5400–5409** — `_authored_commits(repo, _base, _author)`; the worker's own commits are
  selected with `git log -p --author=<me>`.
- **5410–5415** — peers' commits (`_theirs`) are then appended **into the reviewed material**
  as labelled context: `_provenance_block(...)` + `git show -p ... *_theirs`. The label is
  advisory prose; it does not bind the verdict. This is why a peer's `docs/cron-schedules.md`
  and `skills/.../soul-refinement` produced **scope-drift** findings against my cycle, and why
  my own note ("No file, config or state changed") was filed as **fabrication** — the material
  beside it showed 11 changed files, and the reviewer cannot tell which were mine.
- **3129–3140 `ALWAYS_REVIEW_PATHS`**, **5424** — the always-review fail-safe is computed over
  that same whole window. A peer's commit to `ops/scripts/cortex-update.sh` (3137) or
  `mcp-servers/loop-gov-mcp.py` (3131) therefore forces *my* 79-line doc cycle into the
  **heavy/deep** tier — a deep review of someone else's enforcement diff.
- **3179 `REVIEWER_LIGHT_LINE_THRESHOLD`**, `providers.deepseek.request_timeout_seconds: 300`
  — heavy tier + a wide enforcement diff + a 300 s ceiling = the three hang-with-no-verdict
  closes. Which of the two 300 s ceilings fires first is untested — and the operator has settled
  it from the other side (§4a): the reviews must finish INSIDE the ceiling, never be given more
  time. A docs-only 3-file cycle (153 lines, no code) hung at the same ceiling later that
  session, so this is not about the change being risky.

**Three different scopes are in play for one close:**

| Decision | Scope today | Should be |
|---|---|---|
| what is reviewed | lock-start..HEAD, own **+ peer diffs** | own blobs only |
| complexity / tier | lock-start..HEAD (own + peer) | own blobs only |
| receipt blobs (push gate) | push range `merge-base origin/main..HEAD` | unchanged (union coverage) |

## 3. Lever A — session-scoped review range *(enforcement; heavy tier; orchestrator-only)*

Partition the window into own vs peer **blobs**, and let the verdict see only its own.

**A0 — the discriminator A needs does not exist yet (measured 2026-10-18).** Author-based
attribution cannot separate sessions on this host: every session commits under ONE identity.

```
6e98166b esther-agent docs(design): reviews must fit inside 300s…        ← this session
f23f4316 esther-agent docs(evidence): commit the run's gate transcript…  ← cron session
d58006f2 esther-agent fix(review): the window capture must measure…      ← cron session
b291764e esther-agent fix(review): capture the abort's own status…       ← cron session
```

Evidence: `git log --format='%h %an %s'` on this repo. `_authored_commits(repo, base, _author)`
with `--author=esther-agent` matches all four, so **A as first drafted would fail closed into
today's whole-window behaviour and save nothing.** A therefore needs a session discriminator
first:

1. **A1 — a `Cortex-Session: <session_id>` commit trailer, derived from the LIVE governance
   lock.** The `prepare-commit-msg` hook appends the trailer using the session id from the lock
   file the enforcer already required for that commit. It is read from governance state — never
   from an env var the agent exports — so it cannot be forged from prose or spoofed.
2. **A2 — scope the verdict.** `_own_blobs` = blobs whose commit trailer names THIS session.
   Uncommitted (staged/unstaged) paths are **always own** (preserves "uncommitted work counts",
   3118). Fail-closed in the exclusion direction: **no trailer, an unknown session, or an
   unresolvable git state ⇒ the blob STAYS in scope**; only a trailer naming a *different* live
   session excludes. A2 depends on A1 — without it A2 degenerates to today's behaviour (safe, and
   useless).
2. **Material uses own blobs only.** `_theirs` drops from `git show -p` to *names + authors* in
   the provenance block (still disclosed, no longer presented as reviewable content).
3. **Complexity/tier use own blobs.** `_complexity()` keys its line/file counts and the
   always-review check on `_own_blobs`, so a peer's enforcement commit can no longer flip my
   tier.
4. **Receipt records own blobs.** The push gate's union-coverage rule is **untouched** — a
   peer's blob still needs a receipt from *their* session, so nothing ships unreviewed; nobody
   is refused for work they cannot fix.
5. **Fail-closed.** Author unresolvable, git unavailable, or zero `_authored` commits → today's
   whole-window behaviour (5427–5428), unchanged.

## 4. Lever B — diff-derived tiers, one base

- **B1 — unify the base.** Tier and material are computed from the *same* own-blob set and the
  same base. Today they differ (complexity window vs receipt push range), which is how a
  79-line doc change acquired a heavy-tier receipt obligation.
- **B2 — the empty-own-diff class.** Own blobs empty ⇒ **no reviewer call**, because an empty
  diff has exactly one available finding ("your prose is unverified") and so is a guaranteed
  5-minute refusal (cycle 12777). Requirement in exchange: a diagnostic/read-only cycle must
  commit its raw transcript under `docs/evidence/` in the same cycle. That is already the
  reviewer's own stated remedy and is now in `change-checklist`.
- Fail-closed: uncommitted changes present ⇒ never the empty class. Unknown path ⇒
  always-review.

## 4a. Latency requirement (operator, 2026-10-18)

> "900 seconds is ridiculous. the reviews should be shorter than 300s"

Every close review must **complete inside the existing 300 s ceiling** — target p95 **< 120 s**.
**No timeout is raised anywhere**; a slow review is a design defect, not a budget shortfall.
Consequences for the slices above:

1. **Material is the own-blob set (A) with a per-file character budget.** Tonight's refused
   range was 11 files / 448 lines and never returned; bounding what one review must read is the
   fix, and A does it by construction.
2. **Overflow SHRINKS the review, never extends it.** When a whole-range pass would overshoot
   the budget, the existing per-blob re-route (`BLOB_REVIEW_CAP_PER_CLOSE`,
   `BLOB_REVIEW_BUDGET_S`) is the required path — not a longer wait.
3. **A hang is a forbidden outcome.** A review that cannot finish inside the budget must return
   `incomplete: N blobs unreviewed` plus a receipt for the blobs it did judge, and let the
   retry continue from the blob cache. This is lever **D**, deferred in the first draft;
   §4a promotes it to required, because a 300 s hang with no verdict is exactly the failure the
   operator named.
4. **The requirement is measured, not aspirational.** Each close records its review duration
   (seconds) in the store, so a regression becomes visible instead of being felt as friction.

Test: assert every recorded close carries a duration, and that an oversized material routes to
the per-blob path rather than the whole-range call.

## 5. Lever C — local pre-flight before `end_change` *(ordinary work)*

`ops/scripts/manage/review-material.py` already builds the material and already accepts
`--note` (line 102). Add `--check`:

- prints own vs peer blobs (from git), the would-be tier, and the receipt/base it will bind;
- **would-block conditions**, evaluated locally with no model call:
  1. note contradicts the window (note claims "no files changed" while own blobs exist) — the
     exact fabrication finding of cycle 12779;
  2. unverified numeric claims when own blobs are empty;
  3. evidence artifact referenced but not committed;
- exits non-zero when any would-block condition holds.

Wiring: referenced from `change-checklist` Phase 5 and surfaced as a doctor line. **No new
review path** — `change-checklist` forbids a parallel reviewer ("Do not build a parallel review
path AT ALL"); this only evaluates known refusal conditions locally.

## 6. Invariants that must not weaken (asserted, not promised)

1. Every blob in a pushed range still needs a CLEAN verdict from **some** session — union
   coverage unchanged.
2. `ALWAYS_REVIEW_PATHS` still forces review whenever the **own** blob set touches it.
3. Uncommitted work still counts as complex.
4. A peer's commit is still *disclosed* (names + authors) — narrowed, never hidden.
5. No `force`/bypass is added anywhere.

## 7. Tests (each probed BOTH ways)

- `tests/test_review_attribution.py` (real git, already builds own/peer/final-own commits):
  peer always-review blob + own doc blob ⇒ **light** tier, peer blob absent from material;
  **and** own always-review blob ⇒ **heavy**. Existing assertions must not regress.
- `tests/test_reviewer_tier_wiring.py` / `test_gov_friction_fixes.py`: empty own diff ⇒ skip
  **and** skip-with-evidence-required; uncommitted own change ⇒ review runs.
- `tests/test_review_material_bound.py`: `--check` fires on a contradicting note and stays
  silent on a clean one (the "verify the warning both ways" rule).

## 8. Slices (one cycle each — ranges stay reviewable)

0. **D + C** — the bounded close (§4a) and the local pre-flight. Neither needs a discriminator,
   and D is now REQUIRED by §4a rather than deferred, so these two pay off first.
1. **A1** — the discriminator: `ops/install/hooks/` (the `prepare-commit-msg` trailer) plus
   trailer parsing in `mcp-servers/loop-gov-mcp.py`. Enforcement surface, heavy tier, needs the
   change-safety path.
2. **A2 + B** — same file. Own-blob scoping (depends on A1), tier/base unification and the
   empty-own-diff class.

## 9. Risks and open questions

- **Attribution: MEASURED, and it does not work today.** Every commit on this host is authored
  `esther-agent` (evidence in §3), so the author-based path counts a peer's commits as this
  session's own. Verified 2026-10-18 by reading `git log --format='%h %an %s'` after the fifth
  300 s hang. **A1 is therefore a prerequisite, not a refinement.** Its benefit also starts with
  the first commit that CARRIES a trailer: history cannot be retro-fixed, so a cycle closing over
  pre-trailer commits still sees the whole window — safe, just not faster. Until A1 ships, **D and
  C are the only levers that pay off immediately**.
- **Resolved by requirement:** the 300 s ceiling is **not** to be raised (operator, §4a). Which
  ceiling fired first is still unknown and no longer matters — fitting inside it is now the
  design constraint, and lever A removes the cause rather than buying headroom.
- **Cost of being wrong:** if A narrows too far, a genuinely malicious change could ride in a
  peer-attributed blob. Mitigated by union coverage (invariant 1) — that blob cannot be pushed
  without a receipt from its own session, and its diff is still named to the reviewer.

## 10. What this plan is not

Not implemented. Not a reduction in what gets reviewed — a change in **whose work each close
is accountable for**. Enforcement surface, coverage requirement and disclosure all stay. And it
buys no headroom: **no timeout is raised anywhere** (§4a); the review gets smaller and faster
instead.
