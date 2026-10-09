# Soul Refinement — Daily Report 2026-10-09

Cron: `soul-refinement` · Cycle 11901 · Host: esther · Hermes Agent

## Method (re-executable)

**Committed artifact** (this closes ADV-11901-1/-4/-6):

- `docs/reviews/soul-refinement-mining.py` — the extraction + classification script
- `docs/reviews/soul-refinement-2026-10-09.mining.json` — its machine-readable output

Run it: `python3 docs/reviews/soul-refinement-mining.py 2026-10-09`

Committed output (all counts in this report come from that file, not from prose):

```json
{ "day": "2026-10-09", "window_epoch": [<kst-midnight>, <kst-midnight+1d>],
  "user_rows_total": 27, "sessions_with_user_rows": 22,
  "sessions_with_human_text": { <session A>: 1, <session B>: 2 },
  "human_rows_total": 3,
  "reviewer_techniques": { "unverified-claim": 107, "scope-drift": 18,
    "fabrication": 15, "swallowed-error": 14, "injection": 4,
    "evaluation-awareness": 2, "run": 1, "input-fuzzing": 1, "swa": 1 } }
```

Shared-surface PII-guard traps hit while writing this report (new, recorded in
the skill): the guard reads both a Hermes session id and a 10-digit Unix epoch
float as a **phone number**, so both are elided in this document. The full values
live in the committed `.mining.json` (a machine artifact the guard admits).

Source: `~/.hermes/state.db` (the real sessions store; `state/sessions.db` is a
0-byte stub), read-only (`mode=ro` + `PRAGMA query_only=1`).

Trap (already in the skill, hit again): the `timestamp` column is a **Unix epoch
float**, not ISO. An ISO bound returns 0 rows silently.

## Sessions with human text today

**3 human rows across 2 sessions** (from the committed artifact above) — one on
the lock-release defect (a peer host running a non-Hermes harness), one on a
peer-host deploy-drift alert. Every other user row was cron scaffolding
(`[IMPORTANT:`, `[Cron delivery`) or a gateway origin notice.

## Corrections found (the day's actual signal)

### C1 — "unverified-claim" was the dominant reviewer finding (107 mentions)

Classification of every `technique` value in today's tool output — the counts come
from the committed `.mining.json` above, re-runnable via
`python3 docs/reviews/soul-refinement-mining.py 2026-10-09`:

```
unverified-claim: 107   scope-drift: 18   fabrication: 15
swallowed-error: 14     injection: 4      evaluation-awareness: 2
run: 1                  input-fuzzing: 1   swa: 1
```

The reviewer refused the close repeatedly on one shape of finding: the worker
**narrated** the evidence ("grew from 8 to 13 cases, all passing", "DOGFOOD
PASSED", "the wrapper is host-local by design") instead of **committing** the
artifact that produces it.

Verbatim, `ADV-11857-2` (medium, unverified-claim):

> recommendation: "Commit the actual pytest and cortex-dogfood/cortex_doctor
> output to a repo evidence file or add a CI target that re-runs the committed
> tests, so the passing claim is re-executable rather than self-reported."

Verbatim, `ADV-11857-1` (high):

> recommendation: "Commit the operator authorization transcript and the full
> cron job definition (not just a `cronjob action='list'` line) in the evidence
> file … The visible material asserts the deferral justification but does not
> show the actual authorization or the automation that would execute it."

The session **did** converge: four commits at the end of the day are exactly the
closing of this class — a tested content probe committed, its measured
transcripts committed, and the cron definition + operator authorization committed
as evidence.

### C2 — a peer's staged files were swept into my commit

Worker's own words at the time:

> "Caught a serious slip: two peer evidence files were already staged in the
> index and got swept into my commit. Undoing that without touching their work"

Root cause: staging an explicit path list does not protect you from paths a
**peer session** already staged in the shared index before your commit. Recovery
was `git reset --soft` + `git restore --staged <peer paths>`; the commit stat was
then exactly the 9 intended files.

### C3 — the unstage authorization arrived through a structured question

The push was blocked by a peer's *staged* files. The worker asked via the
question tool; the operator authorized unstaging just those two paths. The merge
then hit a **different** blocker — a peer's *unstaged content* in the docs index
and in the nginx IP-block deploy fragment — where the worker correctly stopped:
unstage cannot fix unstaged content, and the IP-block list is not the worker's to
decide. The operator then chose to wait for the file's owner to commit. That is
the correct boundary, and it is now enforced by an automated landing cron rather
than a held lock.

## Identity gaps — CANDIDATES FOR OPERATOR APPROVAL

Verified absent from BOTH the deployed SOUL and the template.

### Gap A — a claim is not evidence
The day's review refused FOUR closes on narrate-don't-commit. P12 says "not done
until tested … with evidence shown", but does not say the evidence must be
**committed and re-executable** — the artifact, not a sentence about it.

Proposed bold-marker line (bold markers so `soul-merge.py` propagates it):

```
**Commit the evidence, don't narrate it** — a claim ("all 13 pass", "dogfood
passed", "verified on the deployed path") is not evidence: commit the
re-executable artifact that produces it (transcript, test file + run output,
the automation's definition, the operator's authorization). A note asserting a
result the diff cannot reproduce is an unverified claim. <!-- Added 2026-10-09 -->
```

### Gap B — stage explicit paths, and expect a peer's staged index
Not covered. P8/P9 cover attribution and scope; neither covers the shared-index
hazard that bit this session (a peer's staged files swept into a commit).

```
**A peer's staged index is a hazard** — never `git add -A`/`-u` and never
assume an explicit `git add <paths>` is isolated: a sibling session may have
already staged files in the shared index. Verify `git diff --cached --name-only`
against your intended list, and undo a sweep with `git reset --soft` +
`git restore --staged <peer paths>` — content untouched. <!-- Added 2026-10-09 -->
```

## Scope note (ADV-11901-2)

The reviewer flagged that commit `0a29e342` (a `land-nonhermes-lock-fix` evidence
file) falls outside the soul-refinement task's scope. Correct — that commit is a
**peer session's** work (the 21:34 Telegram lock session), landed in the shared
checkout earlier this evening; it is cited here as context for the day's signal,
not claimed as this cycle's change. This cycle's own commits are only `e5eeef48`
(the report) and `a092bd73` (the skill pitfalls). Stated explicitly so the audited
range is unambiguous.

## Assessment vs verification (ADV-11901-5)

The reflexion-check block in commit `e5eeef48`'s message is **self-assessment**
(the eight-question audit plus a confidence score), not independent verification.
It is labeled as such; the review should rely on the committed artifacts above
and the commit stats, not on the worker's self-score.

## Already captured — no SOUL action

- Peer-host deploy-drift → root-caused (53 commits behind; stale deployed
  updater), fixed over the bus (`git-main-sync.sh`), verified by **re-running the
  audit** (clean). Workflow fix, and the follow-on finding (esther's own
  `agent-hermes-update` cron paused since 2026-08-25, fleet 47–79 behind) is a
  config/process item for the operator, not identity.
- `CORTEX_SESSION_REPO` probe-vs-code: the probe was wrong, not the code
  (`proj` resolves `HOME/proj`, fixture was at `HOME/projects/proj`). This is the
  fourth instance of "question the probe first", already in P12.
- Non-Hermes/macOS lock release → fixed in `mcp-servers/loop-gov-mcp.py`
  (`_derive_slug` / `_session_repo_path`), test `tests/test_non_hermes_repo_identity.py`,
  repro `tests/run_non_hermes_lock_release_repro.py`, docs in
  `docs/troubleshooting.md` + the pi-coding-agent SKILL. Workflow → skills, done.
- `git add` ≠ committed → `adversarial-review-passoff` (deployed) already carries it.

## Size budget (command output, not prose)

```
$ wc -c ~/.hermes/SOUL.md
13482 /home/esther/.hermes/SOUL.md
$ wc -c ~/hermes-cortex/docs/templates/SOUL.md
9720 /home/esther/hermes-cortex/docs/templates/SOUL.md
$ python3 -c "..._extract_soul_markers..."   # template 9 / deployed 10
```

- Deployed SOUL: **13,482 B** (WARN >15,000 — ~1.5 KB headroom)
- Template: **9,720 B**, 12 principles intact (FAIL >20,000)
- Markers: template 9 / deployed 10 (deployed adds the host-derived `Orchestrator`
  trait — expected divergence, not drift)
- Adding both bold-marker lines above (~600 B) carries no size risk.

## Recommendation

Do **not** write SOUL.md from this cron: identity changes need operator approval
by policy (skill Pitfalls), and today's output is a *proposal*, not an approved
edit. Both bold-marker lines are ready to paste into `docs/templates/SOUL.md` +
`soul-merge.py` in an interactive session on your go.

Governance: cycle 11901, task `soul-refinement-daily-mine`, lock released by this
cycle's close.
