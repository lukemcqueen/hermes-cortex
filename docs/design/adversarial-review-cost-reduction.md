# Adversarial-review cost reduction — plan

**Status: PLAN ONLY. Nothing here is implemented.** Cycle: `adversarial-review-cost-plan`
(12792). Operator: Luke, 2026-10-18. Scope agreed: levers **A + B + C**.

## 1. The problem, measured

Four read-only questions to one agent (00:08–01:35 KST, 2026-10-18) cost **3 governance
cycles, 4 `end_change` attempts, 2 refusals and 3 calls that hit the 300 s ceiling with no
verdict at all** — plus an operator-authorized `force=True` to unwedge the session.

| Cycle | What it was | Result |
|---|---|---|
| 12777 | read-only fan/temp sampling, empty diff | refused — "prose-only claim"; remedy: commit the transcript |
| 12779 | 79-line evidence transcript, 1 file | refused — 3 findings, **all on a peer's commit** |
| 12782 | re-close of the same 79-line artifact | **3 × 300 s timeouts, no verdict**, lock stranded |

Verdicts and timeouts both traced to one thing: **the close reviewed a window that was
two-thirds someone else's work.** The refused range was 11 files / 448 lines across three
sessions (soul-refinement cron, a stalled-rebase session, and mine at 79 lines).

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
  closes. (Hypothesis, not yet proven: which of the two 300 s ceilings fires first is untested.
  Testing it is one config value, listed as an open question below.)

**Three different scopes are in play for one close:**

| Decision | Scope today | Should be |
|---|---|---|
| what is reviewed | lock-start..HEAD, own **+ peer diffs** | own blobs only |
| complexity / tier | lock-start..HEAD (own + peer) | own blobs only |
| receipt blobs (push gate) | push range `merge-base origin/main..HEAD` | unchanged (union coverage) |

## 3. Lever A — session-scoped review range *(enforcement; heavy tier; orchestrator-only)*

Partition the window into own vs peer **blobs**, and let the verdict see only its own.

1. New `_own_blobs(repo, base, author) -> dict[path, sha]`: walk `base..HEAD`
   (`git log --format=%H%x00%ae --name-only`), attribute each path to the commit that last
   touched it in the window, keep the paths whose author resolves to this session. Uncommitted
   (staged/unstaged) paths are **always own** — that preserves today's anti-gaming rule
   ("uncommitted work counts", 3118) and fails closed toward review.
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

1. **A** — `mcp-servers/loop-gov-mcp.py`. Always-review path, heavy tier, change-safety path.
2. **B** — same file. Tier/base unification + empty-own-diff class.
3. **C** — `ops/scripts/manage/review-material.py` + doctor + docs. Ordinary.

## 9. Risks and open questions

- **Attribution depends on git identity resolving.** Tonight's peer commit was distinguishable
  in the material (that is how the findings were *attributable* at all), so the mechanism
  exists — but if a peer session commits under the *same* author email, lever A degenerates to
  today's behaviour via the fail-closed path. Worth verifying with the cron's committer
  identity before building; the lock's `session_id` is the fallback discriminator.
- **Open:** which 300 s ceiling produced tonight's three hangs (MCP client vs
  `providers.deepseek.request_timeout_seconds`). One config value tests it; lever A should
  remove the cause either way.
- **Cost of being wrong:** if A narrows too far, a genuinely malicious change could ride in a
  peer-attributed blob. Mitigated by union coverage (invariant 1) — that blob cannot be pushed
  without a receipt from its own session, and its diff is still named to the reviewer.

## 10. What this plan is not

Not implemented. Not a reduction in what gets reviewed — a change in **whose work each close
is accountable for**. Enforcement surface, coverage requirement and disclosure all stay.
