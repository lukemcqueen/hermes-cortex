# BUILD PLAN — session-scoped review window (A1 trailer + A2 own-blobs)

Cycle `session-scoped-review-window` (13355). Parent design:
`docs/design/adversarial-review-cost-reduction.md` §3 (Lever A), which already carries its own
reviewer findings of 2026-10-18 (ADV-12799-1..4). This delta implements exactly those — no more.

## Reported failure (operator, 2026-10-19, Titus/pi)

Two governed sessions in ONE repo. Session B's close refused on findings naming
`scripts/archive/data_v4_2/build_v4_2_systematic.py` — a file B never touched and that
`git status --short` cannot show, because it was COMMITTED by session A.

## Mechanism, re-read from the code on 2026-10-19

- `mcp-servers/loop-gov-mcp.py:6153` — `_base = git rev-list -1 --before=<lock.started_at> HEAD`:
  the window is TIME-based, so any commit landing after B's lock began is in B's window.
- `:6158` `_authored = _authored_commits(repo, _base, _author)`; `:4163 _agent_author` resolves
  `git config user.email|name`. **One host = one identity**, so A's commits satisfy B's author filter.
- `:6166` the diff body is `git log -p --author=<author> _base..HEAD` — A's diff is IN the material.
- `:6222 _material_scope` and `:4394 _complexity` reuse that author-filtered range, so A's files
  drive B's Diff stat, B's line count and B's always-review tier.
- `:6190 _bound_diff` then truncates the (larger) diff — B's own work can be cut out of its own review.

## The change

### A1 — commit trailer, read from the LIVE lock (never an env var)

New hook `ops/scripts/prepare-commit-msg-session` → deployed to
`<deploy>/hooks/prepare-commit-msg` (global `core.hooksPath`), registered in the deploy map.

- Args: $1 message file, $2 source, $3 sha. **Never blocks a commit** — every path ends `exit 0`
  (Rule 6: this hook runs in EVERY repo on the host).
- Resolves the repo root from the commit's cwd, finds the live lock for THAT repo among
  `<deploy>/state/.governance-*.json` (matching `repo_path` / `repo_slug`), takes `session_id`.
- No lock, no parseable session, unwritable message file ⇒ **no trailer, exit 0** (today's behaviour).
- **Forgery rejected:** every pre-existing `Cortex-Session:` line is REMOVED and exactly one
  authoritative trailer is appended; a hand-written trailer cannot survive a governed commit.
- Idempotent on amend (one trailer, never two).

### A2 — scope the verdict to the cycle's own commits

New helpers in `mcp-servers/loop-gov-mcp.py`:

- `_commit_session(repo, sha)` — the commit's `Cortex-Session:` trailer value, else `""`.
  Two DIFFERENT values, or a malformed line ⇒ `""` (unknown, never a guess).
- `_excluded_session_commits(repo, base, my_session_id)` — SHAs in `base..HEAD` whose trailer names
  a session OTHER than mine. **Fail-closed in the exclusion direction:** no trailer, unknown value,
  empty `my_session_id` for this cycle, or any git error ⇒ NOT excluded.

Wired at four sites, each of which today uses the author-filtered range:

| site | change |
|---|---|
| close `:6158` `_authored` | drop the excluded SHAs |
| close `:6166` diff body | build from the OWN sha list (`git show -p <shas>`) |
| `:6222 _material_scope` | numstat from the same OWN sha list |
| `:4394 _complexity` | same filter; its range numstat from the OWN sha list |

- `_provenance_block` keeps disclosing the rest of the window (names + authors) — a peer's commit is
  NAMED, never reviewed, and never counted toward my tier.
- The always-review fail-safe is computed over the OWN set, so a peer's `mcp-servers/` commit can no
  longer force my docs cycle into the heavy tier.
- **Receipt / push gate UNCHANGED** (union coverage over `merge-base origin/main..HEAD`): a peer's
  blob still needs a receipt from their own cycle, so nothing ships unreviewed.

## Tests (hermetic; real git in tmp_path, no store, no network)

`tests/test_session_scoped_review.py`:
1. `_commit_session` reads a well-formed trailer; `""` for none / malformed / two different values.
2. `_excluded_session_commits` excludes ONLY a different named session; a no-trailer commit stays.
3. Fails closed: empty own session id, git failure, and a body carrying two conflicting trailers.
4. Real tmp repo, both commits by the SAME git identity: A commits `scripts/archive/x.py`,
   B commits its own file → B's own-sha numstat/diff contain ONLY B's file; A's path is named in the
   provenance block, not presented as reviewable content.
5. The hook, driven directly: no lock ⇒ message unchanged; with a lock ⇒ exactly one authoritative
   trailer; a pre-existing forged trailer is replaced; exit code is 0 in every case.

## Out of scope (stated, not silently dropped)

- An UNGOVERNED committer (cron, or a session with no lock) writes no trailer, so its commits stay in
  scope by the fail-closed rule. Excluding them needs a marker the committer must add.
- Rule 26 sequencing: the server-side exclusion is inert until the hook is live, and it is
  fail-closed meanwhile, so both halves ship in THIS change and the deploy reloads both.
