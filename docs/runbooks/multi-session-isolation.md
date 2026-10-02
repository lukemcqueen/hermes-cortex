# Runbook — Running Multiple Sessions on One Host Without Collisions

**Use when:** more than one agent session runs on the same host, or a session
discovers another session's work in its tree, or commits are attributed to the
wrong session, or two sessions fight over the enforcement lock.

---

## 1. The problem, concretely

One host, two sessions, one repo. Observed 2026-10-02:

- **Shared git index.** Session A's staged 20-line edit landed inside session B's
  commit (`e40139b6`) — B's `git commit` swept A's staged work. Nothing was lost,
  but authorship was wrong and A's change shipped under B's message.
- **Identical authorship.** `agent.env` carries a single `AGENT_NAME`, so both
  sessions committed as the same author. The close-gate's author-scoping (which
  decides what a cycle is responsible for) cannot distinguish them.
- **Deploy collision.** Both ran `cortex-update.sh`. Every run unlocks the
  enforcement files then relocks; two concurrent runs interleave, and a run that
  exits non-zero **after** its unlock leaves the files unlocked. The immutable
  flags came off twice in one session, and the auditor rightly alerted.
- **Shared handoff state.** `state/pending-update-results/` is host-global, so a
  dead worker's marker appears in another session's sweep.

## 2. The principle

**Scope what can be scoped; serialise what cannot.**

| Scoped per session | Serialised per host |
|---|---|
| git identity (authorship) | deploy (`cortex-update.sh`) |
| working tree + index | immutable enforcement flags |
| governance lock file (`.governance-<session>.json`) | package installs |
| loop-gov DB rows (`session_id`) | the deployed enforcement tree itself |
| task rows, session state | |

There is exactly **one** deployed enforcement tree. Concurrency there must be
*excluded* by a lock, never "scoped" — scoping a shared resource only produces two
sessions that each believe they own it.

## 3. The convention

**One session = one worktree = one branch = one identity.**

```bash
# from the primary checkout
ops/scripts/manage/session-identity.sh new pi        # worktree + branch session/pi + identity
cd ~/hc-session-pi                                   # run the session THERE

ops/scripts/manage/session-identity.sh show          # what am I, where, as whom
```

`new` creates the worktree from `origin/main` (so a peer's uncommitted work is
never inherited) and sets a session-scoped identity.

### Identity rules

- The git identity becomes `<agent>-<tag>` / `<agent>+<tag>@<domain>`
  (e.g. `esther-agent+2`, `esther+2@hermes.local`). A plain `2`, `3` is fine.
- **`AGENT_NAME` is never session-appended.** It is the bus/routing identity
  (it decides the `inbox_<agent>` queue and the on-bus name). Appending a session
  tag to it would break routing. `session-identity.sh` asserts it is unchanged
  before returning.
- Per-worktree identity requires `extensions.worktreeConfig=true`; without it,
  `git config` inside a worktree writes to the **shared** config and silently
  changes every other worktree's identity (observed — the primary tree picked up
  the session identity). The script sets it.

## 4. Verification

```bash
git worktree list
git -C <primary>   config user.name && git -C <primary>   config user.email
git -C <worktree>  config user.name && git -C <worktree>  config user.email   # must differ
grep AGENT_NAME ~/.hermes-cortex/agent.env                                    # must be UNCHANGED
```

A commit made in each tree must be authored by its own identity — check with
`git log -1 --format='%h %an <%ae>'`.

## 5. Pitfalls

- **Never work in the primary tree while another session does.** That is the
  index-sweep collision. Use a worktree.
- **Setting an identity without `--worktree` scope changes the shared config.**
  See §3.
- **Do not create a worktree from a dirty tree.** `new` branches from
  `origin/main` deliberately; branching from HEAD would carry a peer's WIP.
- **Deploy is host-wide.** A worktree isolates your *editing*, not your
  *deploying*. Only one session should run `cortex-update.sh` at a time; a run
  that exits non-zero can leave the enforcement files unlocked — re-check with
  `hermes-plugin-lock status` and re-apply `sudo hermes-plugin-lock lock`.
- **Removing a worktree:** `git worktree remove <path>` — do not `rm -rf` it, or
  the primary's worktree metadata goes stale.

## Related

- `docs/runbooks/cron-model-chain-repoint.md` — the other per-host control point
- `skills/devops/governance-lock-lifecycle/SKILL.md` — lock states and clearing
- `skills/devops/loop-governance/SKILL.md` — cycles, scoring, close-out
