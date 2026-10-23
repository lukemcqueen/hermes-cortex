# Enforcement Plumbing Verification — 2026-10-23 (after gateway restart)

## Provenance

- Produced by Titus session `verify-enforcement-plumbing` + follow-ups, governance cycles
  7442 / 7445 / 7447 (lock `20261023_172042_b4605c`), host macOS LAM2.local.
- User action under test: `hermes gateway restart` after the 2026-10-23 pull+deploy
  (tip `2a1517c6`; deploy wrote loop-gov-mcp + enforcer at 17:23:03; gateway restarted
  17:29:58).
- Host paths normalised (`/Users/luke` → `~`) in this committed copy.

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

## 2. The residual bug found (WRONG_REPO near-miss on a correctly-tagged lock)

Cycle 7442 (read-only verification, opened 17:36:58, lock correctly tagged
`repo_slug=hermes-cortex` / `repo_path=~/hermes-cortex` with the session repo hint file
present since 17:25:34) was REFUSED on close with:

```text
Cannot close: the lock's repo cannot contain this session's work.
  Lock repo_slug : 'hermes-cortex'  ->  /Users/luke/hermes-cortex
  In that repo   : no commits in the window.
  Work found in  : /Users/luke/Developer/AI/steadfaste-s1-model
```

Two things are wrong, both measured:

1. **session_repo reached the guard as None** — the refusal message omits the
   `Session repo : ...` line (printed only when session_repo is not None), so the
   guard's tag-agreement escape could NOT fire even though the lock's own repo_path
   was correct and the enforcer's hint file for the session existed. This is the
   deploy-not-load trap in MCP-child form: the refusal likely came from the
   pre-deploy MCP child (10417, PID alive since 17:20:43, parented to gateway 10393
   from 17:20:40) running the pre-pull guard code and pre-pull session-repo injection.
   The identical close retried as cycle 7445 closed CLEANLY — the new child (43193)
   had taken over and the tag-agreement escape worked.

2. **The elsewhere-attribution filter uses the candidate repo's OWN git identity, not
   the agent's.** `_agent_author(repo)` (loop-gov-mcp.py `_agent_author`, line ~4591)
   reads `git config user.email/name` of the repo it is asked about. The refusal named
   `~/Developer/AI/steadfaste-s1-model` — a repo whose git identity differs from the
   agent's own (the repo's configured identity is the repository OWNER's, while the
   hermes-cortex repo is configured with the AGENT's identity). ANOTHER session
   (cycles 7443/7444, sess_6459cc640a9c) is ACTIVELY committing there (18 commits in
   the window authored under that repo's configured identity). Because that repo's own
   git config IS that identity, the guard treats those peer commits as "commits THIS
   AGENT authored" — but they are not the current agent's. On a multi-identity dev
   host the "attributed candidates only" narrowing can therefore still accuse the
   session of working in a repo it never touched. The lock-side test applies the same
   bar only when the candidate repo's identity happens to equal the agent's.

Fix direction for the orchestrator: resolve "this agent" from the agent.env identity
(per AGENTS.md rule 21 — the hooks' own source of git authorship) or exclude commits
carrying a different `Cortex-Session:` trailer (`_excluded_session_commits` already
exists for exactly this), instead of trusting each candidate repo's own git config.

## 3. Environment facts

- Two loop-gov-mcp.py children observed alive at verification time:
  - 10417 — cortex venv, started 17:20:43 (BEFORE the pull/deploy finished at 17:23:03)
    → holds PRE-PULL guard code in memory; parent 10393 (gateway-ish, 17:20:40).
  - 43193 — cortex venv, started 17:30:04 (AFTER the restart) under new gateway 43169
    → holds the deployed code.
- The lingering pre-restart child 10417 is the likeliest reason cycle 7442 was served by
  old rules; it should not remain after a clean restart (operator check: whether the old
  gateway 10393 was actually terminated).
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

Enforcement plumbing after the gateway restart is FUNCTIONAL for the current session:
control flow (MCP server initialised), plugin loaded from the deployed file, doctor
clean, lock tagged with repo identity, and an end-to-end close works. Residual risk
recorded: (a) a stale pre-restart MCP child/gateway may still serve some sessions with
pre-pull guard code (WRONG_REPO false refusal), and (b) the new guard's
elsewhere-attribution still trusts candidate-repo git identity rather than the agent's
own — both need an orchestrator decision; this doc is the evidence for it.
