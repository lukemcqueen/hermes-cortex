# Enforcement Plumbing Verification — 2026-10-23 (after gateway restart)

## Provenance

- Produced by Titus session `verify-enforcement-plumbing` + follow-ups, governance cycles
  7442 / 7445 / 7447 / 7453 / 7454 (lock `20261023_172042_b4605c`), host macOS LAM2.local.
- User action under test: `hermes gateway restart` after the 2026-10-23 pull+deploy
  (tip `2a1517c6`; deploy wrote loop-gov-mcp + enforcer at 17:23:03; gateway restarted
  17:29:58).
- Host paths normalised (`/Users/luke` → `~`) in this committed copy.
- CORRECTION (second pass, cycle 7454): the first version of this doc attributed the
  7442 refusal in part to the pulled guard's author-identity filter. Re-verification
  proved the simpler cause — the refusal was served by the STALE pre-restart MCP child
  running the PRE-PULL guard. See section 2. The author-identity observation remains a
  latent design note, not the operative cause.

## 1. What works (verified with live tool output)

- **New enforcer loaded**: gateway supervisor PID 43147 started 17:29:58 — AFTER the
  deploy wrote the new plugin (17:23:03) — so the RUNNING gateway executes the deployed
  enforcer, not the old in-memory copy. Doctor no longer prints the
  "GATEWAY RESTART REQUIRED / Restart the gateway to load the new loop-governance module"
  item (0 matches post-restart vs 1 pre-restart).
- **begin_change now tags the lock with repo identity**: lock file
  `~/.hermes-cortex/state/.governance-20261023_172042_b4605c.json` carries
  `repo_slug: hermes-cortex`, `repo_path: ~/hermes-cortex`. Before the restart the same
  session's first lock had EMPTY repo identity (close wrote no receipt); after the
  restart the injected identity is present and cycle 7445 closed cleanly with a receipt.
- **Loop-governance MCP current**: fresh child PID 43193 (17:30:04, cortex venv) spawned
  under the new gateway (43169) AFTER the deploy — it loaded the post-pull
  `loop-gov-mcp.py` (deployed 17:23:03). A stale pre-deploy child 10417 (17:20:43) still
  lingers (see section 3).
- **Enforcement files immutable**: `uchg` flag on
  `~/.hermes/plugins/governance-enforcer/__init__.py`,
  `~/.hermes-cortex/scripts/hermes-plugin-lock`, `~/.hermes-cortex/hooks/post-merge`.
- **Plugin enabled**: `hermes plugins list` shows governance-enforcer enabled.
- **Doctor**: 471 pass · 12 warn (all disposed) · 1 fail — the ONLY fail is the
  pre-existing out-of-scope `AGENTS.md (steadfaste)` on a DIFFERENT repo, accepted by the
  fleet's own verify script. All governance/hook/lock/checksum checks pass.
- **Full cycle close works end-to-end**: cycle 7445 (open, score, close) completed
  cleanly with repo identity and NO wrong-repo refusal — the new guard's
  tag-agreement escape fired. This is the live proof that a normal governed cycle
  round-trips after the restart.

## 2. The finding, corrected: the 7442 refusal was served by the STALE pre-restart MCP child

Cycle 7442 (read-only verification, opened 17:36:58, lock correctly tagged
`repo_slug=hermes-cortex` / `repo_path=~/hermes-cortex` with the session repo hint file
present since 17:25:34) was REFUSED on close with:

```text
Cannot close: the lock's repo cannot contain this session's work.
  Lock repo_slug : 'hermes-cortex'  ->  /Users/luke/hermes-cortex
  In that repo   : no commits in the window.
  Work found in  : /Users/luke/Developer/AI/steadfaste-s1-model
```

**Proven cause — stale MCP child, not the pulled guard.** Two loop-gov-mcp.py children
were alive at the time:

- 10417 — cortex venv, started 17:20:43 (BEFORE the pull finished at 17:23:03), parent
  10393 (gateway-ish, 17:20:40) → it imported the PRE-PULL `loop-gov-mcp.py` into
  memory and never re-imported. The pre-pull guard (base 7230c79c) has NO
  `_session_repo_agrees` escape and NO `Session repo :` output line — it refuses
  whenever the lock's repo shows no window commits AND any OTHER candidate repo gained
  commits (`_repos_with_window_work`, unattributed). The 7442 refusal text has no
  `Session repo :` line, matching the base guard exactly.
- 43193 — cortex venv, started 17:30:04 (AFTER the restart, under new gateway 43169)
  → holds the DEPLOYED (post-pull) guard with the 2026-10-23 narrowing and the
  tag-agreement escape.

Decisive re-test: cycles 7445, 7447 and 7453 — opened under the SAME conditions (the
peer session in steadfaste-s1-model was STILL committing) — all closed CLEANLY once the
session's calls were served by the new child 43193. The same close that refused under
the old child passed under the new child. The refusal was the known deploy-not-load
trap in MCP-child form: **the restart created a NEW gateway but the OLD gateway (10393)
and its MCP child (10417) were never terminated** — both were still alive at
verification time (~17:50), and a session still routed through them ran the pre-pull
guard rules.

**Latent design note (not the operative cause):** in the CURRENT guard,
`_agent_author(repo)` (loop-gov-mcp.py, line ~4591) reads the candidate repo's OWN
`git config` identity, not the agent's identity from agent.env. On a multi-identity dev
host the candidate filter can match a peer's commits authored under that repo's
configured identity, as steadfaste-s1-model's commits are (repo configured with the
owner's identity, not the agent's). This only bites when session_repo is also unknown
(the tag-agreement escape covers the common case where it resolves). Worth an
orchestrator look — resolve "this agent" from agent.env or exclude other sessions via
the `Cortex-Session:` trailer — but it did NOT cause the 7442 refusal, which came from
pre-pull code.

**Operator action:** confirm the old gateway 10393 (and its loop-gov child 10417) is
terminated, so no session is served by pre-pull guard code while the new gateway runs.

## 3. Environment facts

- Two loop-gov-mcp.py children observed alive at verification time AND at re-verification
  (~17:50):
  - 10417 — cortex venv, started 17:20:43 (BEFORE the pull/deploy finished at 17:23:03)
    → holds PRE-PULL guard code in memory; parent 10393 (gateway-ish, 17:20:40), itself
    still alive.
  - 43193 — cortex venv, started 17:30:04 (AFTER the restart) under new gateway 43169
    → holds the deployed code. Sessions served by it closed cleanly (7445/7447/7453).
- The lingering pre-restart gateway 10393 + child 10417 are the reason cycle 7442 was
  served by old rules. This is a clean-up item for the operator, not a code defect in
  the deployed guard.
- The peer session committing in steadfaste-s1-model is real and active (PENDING cycles
  7443/7444 in sess_6459cc640a9c); its commits are NOT Titus's work.

## 4. Pre-existing macOS test failures (NOT caused by this pull)

The pulled tests include 3 failures on macOS, all the same class — the enforcer/MCP
correctly records git-RESOLVED paths (`/private/var/folders/...`) while the tests assert
the raw `tempfile.mkdtemp` path (`/var/folders/...`); macOS symlinks `/var` to
`/private/var`, Linux does not, so they pass on Linux and fail here:

- tests/test_loop_gov_review_repo.py::test_enforcer_records_and_injects_an_absolute_repo_path
- tests/test_loop_gov_cli.py::test_cli_stamps_the_cwd_repo_not_the_host_canonical
- tests/test_loop_gov_cli.py::test_cli_begin_change_locks_the_cwd_repo_end_to_end

Verified PRE-EXISTING at the pull's base (7230c79c) in a detached worktree — identical
failures, same runner. 17 other tests in the file pass. Not a regression from this pull;
fix belongs to the orchestrator (compare `str(deep.resolve())` / `str(proj.resolve())`).

## Result

Enforcement plumbing after the gateway restart is FUNCTIONAL: control flow (MCP server
initialised), plugin loaded from the deployed file, doctor clean, lock tagged with repo
identity, and end-to-end closes work (7445/7447/7453). The one refusal (7442) was
served by a STALE pre-restart MCP child (old gateway 10393 + child 10417, both still
alive) running PRE-PULL guard code — the known deploy-not-load trap, resolvable by
terminating the old gateway. A latent design note for the orchestrator: the CURRENT
guard's elsewhere-attribution reads the candidate repo's own git identity rather than
agent.env, which can mis-attribute a peer's commits on multi-identity hosts — worth a
look, but not the cause of the refusal.
