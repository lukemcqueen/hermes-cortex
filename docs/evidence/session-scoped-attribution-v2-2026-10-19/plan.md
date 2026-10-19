# BUILD PLAN — truly session-scoped attribution (cycle 13365)

**IMPLEMENTED in this cycle (D1′, D2):** attribution now DISAMBIGUATES by session activity, from the
data that already exists — the lock file is rewritten by the server on every governed call, so its
**mtime is that session's last governed activity**. The hook stamps the single *fresh* claimant
(within `CORTEX_SESSION_ACTIVE_TTL`, default 90s); zero fresh + a single claimant ⇒ that claimant;
zero or ≥2 fresh claimants ⇒ **no trailer** at all. That covers 2–3 sessions in one repo; when
sessions cannot be told apart the commit stays in scope for everyone (fail-closed) instead of being
silently credited to the wrong one. Deviation from D1 as drafted: no new `.active-*` file is written —
the existing lock's mtime carries the same signal, so nothing new can be forgotten or drift.

**Still to build:** nothing — D3 and D4 shipped in cycle 13368:
D3 scopes the per-blob DEMAND list to the session that authored each blob's current content
(`_peer_session_range_paths`; peer-attributed paths are dropped from the demand and the receipt, so
the push gate still refuses the range until the OWNER closes its own cycle); D4 adds a doctor check
that WARNS when a repo has more than one live lock.

Operator: Luke, 2026-10-19: *"you should fix this so that it is truly session scoped! you can
assume 2 or 3 sessions in one repo"*.

## 1. The defect, measured

Two sessions in one repo. On the affected host:

```
$ ls -1 ~/.hermes-cortex/state/.governance-*.json
.governance-sess_6459cc640a9c.json
.governance-sess_cb06267f73e5.json
$ grep -H '"repo_path"' ~/.hermes-cortex/state/.governance-*.json
…sess_6459cc640a9c.json:  "repo_path": "/Users/luke/Developer/AI/steadfaste-s1-model"
…sess_cb06267f73e5.json:  "repo_path": "/Users/luke/Developer/KOSCAP/koscap-mwi"
$ git -C …/steadfaste-s1-model log --format='%h %s%n  trailer=%(trailers:key=Cortex-Session,valueonly)' -5
9846266 Pre-register the validation checks and the rule for changing them
  trailer=sess_6459cc640a9c
f35e741 Make the package installable from src/ layout (no sys.path juggling)
  trailer=sess_6459cc640a9c
…
$ git -C …/steadfaste-s1-model status --short     # (empty — the files are COMMITTED, not dirty)
```

One lock per repo, eight unpushed commits in `steadfaste-s1-model`, **every commit stamped with the
single repo lock's id**. The consumer excludes only a *different* session, so the peer's commits
count as the caller's and the per-blob demand (whole unpushed range) reviews a peer's files.

Root cause, in the code:

- locks are already unique **per session** — `_read_lock`/`_write_lock` use
  `_session_lock_path(session_id)` → `.governance-<session_id>.json`, atomically written
  (`mcp-servers/loop-gov-mcp.py:2338-2379`);
- **but the write gate is per REPO**: the enforcer's check is "a lock exists for this repo", so a
  second session needs no lock of its own — it rides the first session's;
- the hook then resolves attribution by *repo path* and stamps the one matching lock
  (`ops/scripts/prepare-commit-msg-session`, `SESSION=` block);
- git carries no session identity, so any hook that "picks the matching lock" is guessing, and here
  the guess is systematically wrong.

## 2. Design

### D1 — the always-current local lock (new primitive, consumer-first)

A per-session file the committing session's own process writes on **every governed call**:

```
<state>/.active-<session_id>.json
{"session_id": …, "repo_path": …, "repo_slug": …, "started_at": …,
 "last_call_at": "<iso>", "last_call_tool": "write_file", "pid": <mcp server pid>}
```

Writer: the loop-governance server, in the same place it refreshes the lock heartbeat (one call site,
`_touch_lock`), so it costs no new agent step and cannot be forgotten.

### D2 — attribution rule in the hook (fail-closed, N-safe)

```
candidates = locks whose repo_path == this repo   (existing path match)
fresh      = candidates whose .active marker is within ACTIVE_TTL (default 90s)
SESSION    = the single session id in fresh            if exactly one
           | the single id in candidates               if zero fresh AND exactly one candidate
           | (write NO trailer)                        otherwise   # 0 or ≥2 candidates
```

- **≥2 sessions acting in one repo within `ACTIVE_TTL` ⇒ NO trailer.** With 2–3 sessions the markers
  usually separate by activity, and when they do not, silence is honest: the window fails closed.
- This subsumes the two shipped rules (foreign-repo lock ignored; several locks ⇒ no stamp) and adds
  the freshness discriminator that makes 2–3 sessions in one repo genuinely separable.

### D3 — the consumer scopes everything to the attributed session

`_own_commit_shas` is already wired into the material, the Diff stat and `_complexity`. Extend it to
the **per-blob demand list** (`_push_range_blobs` → the review's blob set): a blob whose commit is
attributed to another session is **not** demanded of this session; it is disclosed by name and left
to that session's own cycle (the peer must close it). Ambiguous attribution ⇒ blob stays demanded
(fail-closed, unchanged from today).

### D4 — detection, so this is visible rather than archaeology

Doctor `WARN` when (a) a repo has ≥2 live locks, or (b) a commit in the push range carries no
trailer while a repo lock exists (the fallback case), naming the paths involved.

## 3. Fail-closed matrix (asserted in tests)

| locks for this repo | fresh markers | trailer written |
|---|---|---|
| 1 | 1 (that session) | that session id |
| 1 | 0 | that session id (single-candidate fallback) |
| 2–3 | 1 | that session id |
| 2–3 | 0 | **none** |
| 2–3 | ≥2 | **none** |
| 0 | — | none (today's behaviour) |

## 4. Tests (hermetic, real `git init`, no store)

1. `test_hook_attributes_by_fresh_marker_among_two_sessions` — two locks + one fresh marker ⇒ that id.
2. `test_hook_is_silent_with_two_fresh_markers` — two fresh ⇒ no trailer.
3. `test_hook_falls_back_to_the_single_candidate` — one lock, stale marker ⇒ still stamped.
4. `test_hook_ignores_a_foreign_repo_lock` (exists) and
   `test_hook_writes_nothing_when_two_locks_share_this_repo` (exists) — must stay green.
5. `test_peer_session_blob_is_not_demanded` — the per-blob set excludes a peer-attributed blob and
   still names it.
6. `test_ambiguous_blob_stays_demanded` — no trailer ⇒ still demanded.

## 5. Honest limits

- Commits made **before** this ships cannot be re-attributed: their trailer is wrong or absent, so
  they stay in scope. A wrong trailer can only be corrected by a new commit.
- A change landed by a session that never runs the loop-governance server (no lock, no marker) is
  unattributable by construction ⇒ stays in scope, disclosed.
- `ACTIVE_TTL` trades separation against silence: too long merges sessions, too short produces "no
  trailer". 90s covers a govemed call → edit → commit loop; it is a constant in ONE place.
