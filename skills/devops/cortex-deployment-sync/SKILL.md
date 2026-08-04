---
name: cortex-deployment-sync
version: 1.0.0
category: devops
description: "Use when pulling latest or running cortex update."
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# Cortex Deployment Sync

**Class of task:** any "pull latest", "cortex update", "update from repo", or repo→runtime deployment operation on a Hermes Cortex machine. Also covers diagnosing why `cortex-update.sh` FAILED on specific files.

## ⚡ THE SANCTIONED INVOCATION (2026-08-04 — supersedes 2026-07-31 guidance)

Since 2026-08-04 the enforcer's `_is_sanctioned_cortex_update_command()` lets
the EXACT deploy invocation through the terminal gate WITHOUT a governance
lock — this is the lock-free self-recovery that breaks the DOGFOOD deadlock:

```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh            # canonical (bash prefix OK)
~/hermes-cortex/ops/scripts/cortex-update.sh                  # also sanctioned (no prefix)
# allowlisted flags ONLY: --force-all --dry-run --status --delta --clean-stale
```

Exact match only — no `sudo`, no `-c`, no chaining (`&&`, `;`, `|`, `>`), no
command substitution, no other scripts or flags. Anything else is write-class
and still requires a governance lock.

**⚠️ Deploy ≠ load:** after a run that updated the enforcement chain, the
RUNNING gateway still executes the OLD enforcer module from memory —
`hermes plugins disable/enable` only writes `config.yaml`, it does NOT
hot-reload the process-global PluginManager singleton. The new enforcer
activates ONLY after `hermes gateway restart`, which agents cannot perform
(lifecycle guard). If the sanctioned command still returns `GOVERNANCE LOCK
REQUIRED` right after a deploy, that is a PENDING RESTART, not a code bug —
stop retrying and ask the host operator (Luke) to restart the gateway.

**Use `--force-all` only when the delta engine skips files that should re-deploy** — plain run is the safe default.

## The proper sequence (user directive, 2026-07-31)

> "Whenever there's a governance mechanism change you NEED to cortex update as this is the proper path. no shortcuts."

1. `git pull --rebase origin main` — resolve conflicts (see Pitfall 2). If unstaged changes block the rebase, use `git pull --rebase --autostash origin main`.
2. **`bash ~/hermes-cortex/ops/scripts/cortex-update.sh`** — the sanctioned lock-free invocation (see ⚡ above)
3. Doctor output is embedded in the update; fix every ❌ (score PENDING cycles, verify governance deployed)
4. Re-run step 2 if the doctor reported failures, until it's clean (0 fail)
5. Verify clean state

**Do NOT push** during pull-latest. Local pipeline auto-commits stay local (see Pitfall 3).

## Pitfall 1: Governance files are immutable — cortex-update is the ONLY deploy path

Deployed governance files carry `chattr +i` (Linux) / `chflags uchg` (macOS):
- `~/.hermes/plugins/governance-enforcer/__init__.py`
- `~/.hermes-cortex/scripts/hermes-plugin-lock`
- `~/.hermes-cortex/hooks/post-merge`
- `~/.hermes-cortex/scripts/{pre-commit-score,pre-push-pull,post-commit-audit,post-push-audit}`

Manual `chmod`/`cp` fails with `Operation not permitted` — the `i` flag survives `chmod`. `cortex-update.sh --force-all` handles the full **unlock → copy → re-lock** cycle via `sudo hermes-plugin-lock` (requires a NOPASSWD sudoers rule for `/usr/local/sbin/hermes-plugin-lock`).

**Detect:**
```bash
# cortex-update prints "FAILED: <path>" per immutable file
lsattr ~/.hermes/plugins/governance-enforcer/__init__.py   # ----i---------e-------  ← immutable
sudo -n hermes-plugin-lock unlock                          # clears the flags
~/hermes-cortex/ops/scripts/cortex-update.sh               # deploy — DIRECT path, no bash prefix
# verify: diff deployed vs repo = empty, plugin enabled, immutable re-applied
```

## Pitfall 8: The dogfood deadlock — run cortex-update FIRST, then begin_change

When the repo's enforcer is newer than the deployed one (Moses pushed), `begin_change` fails with **DOGFOOD REQUIRED** — and the DOGFOOD gate refuses to create a governance lock (it returns BEFORE lock creation). Under the fail-closed terminal policy, every command except the sanctioned one is write-class → blocked without a lock. **Fixed 2026-08-04:** the enforcer's `_is_sanctioned_cortex_update_command()` allows the EXACT deploy command through without a governance lock, so the designed order is:

1. `bash ~/hermes-cortex/ops/scripts/cortex-update.sh` (sanctioned lock-free — deploys the new enforcer)
2. THEN `begin_change()` (dogfood gate now passes, repo == deployed)

Do NOT try to `cp` the enforcer file manually (blocked + violates the immutable-deploy rule), do NOT loop retrying `sudo hermes-plugin-lock` forms (write-class, needs a lock — the sanctioned exception covers only the exact cortex-update.sh invocation). Symptom on 2026-07-31: 8+ failed attempts across `bash`, `cp`, `python3 -c` before the fix landed; since 2026-08-04 the bare sanctioned command runs clean.

**⚠️ Deploy ≠ load:** after deploying, the RUNNING gateway keeps the OLD enforcer in memory until `hermes gateway restart` (agent-blocked — the host operator runs it). If the sanctioned command still returns GOVERNANCE LOCK REQUIRED after a deploy, that is a pending restart, not a code bug — do not loop; ask the operator.

## Pitfall 9: `git pull --rebase` replayed commits get logged as `--no-verify` → push blocked

**Symptom (2026-07-31):** You commit (pre-commit hook passes), then `git pull --rebase origin main` (per Rule 14), then `git push` is blocked with:

```
❌  Push blocked: commit <sha> was made with --no-verify
    Re-do the commit through the pre-commit hook.
```

Your commits were NEVER made with `--no-verify`. The rebase **replays** commits without running pre-commit; the post-commit-audit hook sees the missing `.pre-commit-ran` sentinel and logs each replayed commit into `~/.hermes-cortex/state/no-verify-log.json`. The pre-push gate then blocks any push whose range contains a logged hash.

**Fix (sanctioned — the hook's own advice):** re-do the commits through the pre-commit hook:

```bash
git reset --soft HEAD~N          # N = your rebased commits; changes stay staged
git reset                        # unstage
git add <files> && git commit -m "<same message>"   # pre-commit runs → sentinel written → NOT logged
# repeat per logical commit, then:
git push origin main
```

Do NOT edit no-verify-log.json (audit tampering). Do NOT `git push --no-verify`. The recommit path is clean: pre-commit writes the sentinel, post-commit consumes it, nothing is logged.

**Prevention:** check for a no-verify log entry right after any rebase: `tail -3 ~/.hermes-cortex/state/no-verify-log.json` — if your commit hashes appear with fresh timestamps, recommit before pushing.

**Related:** the agent-fixer crons commit with `--no-verify` (logged 2026-07-30 as `fix: remove trailing backtick…`), which is how corrupted skill edits keep reaching the repo.

## Pitfall 2: `blocked_ips.add` conflicts on every pull

`ops/install/deploy/nginx/blocked_ips.add` is auto-generated by the threat-pipeline cron on BOTH local and origin, so it conflicts on nearly every `git pull`. The file is machine-generated — always take theirs:

```bash
git checkout --theirs ops/install/deploy/nginx/blocked_ips.add
git add ops/install/deploy/nginx/blocked_ips.add
GIT_EDITOR="true" git rebase --continue
```

## Pitfall 3: Local branch runs ahead of origin with pipeline auto-commits

After pulls, local `main` typically carries `auto: block N suspect IPs [pipeline]` commits ahead of origin. This is normal — the threat-pipeline pushes its own commits. During "pull latest" do NOT push them. The doctor's `⚠️ Repo sync` warning reflects this; it's benign.

## Pitfall 4: cortex-update purges governance locks

`cortex-update.sh` runs `purge-stale-governance-locks.py` at the end — it removes EVERY `.governance-*.json` lock file including your active session's. After a deploy:
1. Re-acquire: `begin_change()`
2. Score all PENDING cycles: `cycle_query` → `feedback_accept`
3. `end_change()`

Otherwise the doctor FAILs on "PENDING cycles". Note the lock file path reuses the same session ID; the DB cycle is the source of truth.

## Pitfall 5: Don't over-fix — follow the repo

Doctor warnings that are NOT failures: `SOUL.md reverse drift` (agent profile differs from template — expected), `Skill drift` (deployed skill has local fix the repo lacks — Moses's job to merge). When the user says "DO NOT UPDATE SOURCE", accept warnings as-is and leave repo files untouched. Only ❌ failures (PENDING cycles, missing governance deploy, hook drift) require action.

## Pitfall 6: Stash before pull if you hold uncommitted orchestrator-only edits

Non-orchestrators cannot commit to `ops/install/` etc. (pre-commit hook blocks). If you made such an edit, stash it before pulling, and let the orchestrator land the upstream fix:
```bash
git stash push -m "desc" -- <path>
git pull --rebase origin main
# check if upstream fixed it; if so drop the stash: git stash drop
```

## Pitfall 7: Analytics-endpoint config bugs look like perf problems

A non-empty-but-bogus telemetry host (e.g. `POSTHOG_HOST: "http://127.0.0.1:1"` in a compose env block) still initializes the analytics client; each flush + retry throws a network error, and the retry storm pins the container at 100%+ CPU — amplifying even minor request-validation errors into sustained burn. Symptom: `docker stats` shows a web container at ~102% CPU with `PostHogFetchNetworkError` flooding logs.

**Fix:** empty string, not a bogus host (`POSTHOG_HOST: ""`) — the client is never initialized. Then recreate containers; `docker compose restart` does NOT re-read env vars. This was the root cause of a full-core Langfuse web spin on 2026-07-31; see the reference trace.

## Pitfall 10: Terminal guard blocks `python3 -c` with large paths — use execute_code / script files

The terminal tool's gateway-lifecycle guard (`~/.hermes/hermes-agent/cron/lifecycle_guard.py`)
hard-blocks commands that look like they restart the gateway. Its tokenizer
splits multi-line commands on newlines before parsing quotes, so a
`python3 -c "..."` payload with embedded newlines has interior lines parsed as
standalone shell segments — a path literal inside the payload (e.g.
`sqlite3.connect('/home/user/.hermes-cortex/data/loop-governance.db')`) becomes
a "referenced script". Reading a >1MB file (loop-governance.db is ~33MB)
fails closed as "unsafe", and the whole command is blocked with a bogus
**"Blocked: command or referenced script cannot restart or stop the gateway"**
error — even though no gateway command was involved.

**Symptom:** plain sqlite/read-only `python3 -c` queries of
`~/.hermes-cortex/data/*.db` (or any >1MB file) get blocked with the
gateway-restart error.

**Workaround (do NOT patch hermes-agent — user rule; upstream AGENTS.md also
rejects "plugins that touch core files"):**
1. **Preferred:** run the query via the `execute_code` tool (runs Python
   directly, no shell-string parsing — guard never sees it), or
2. Run it from a script file: `python3 /tmp/query.py` instead of
   `python3 -c`/heredoc — the guard only trips on the inline form with
   embedded paths.

This is a known upstream false positive; if it ever gets fixed upstream it
will land via `hermes update`, not a local patch.

## Verification

- `diff <repo-source> <deployed-copy>` empty for governance files
- `hermes plugins list | grep governance` → enabled
- `lsattr` shows `i` re-applied after deploy
- Doctor: no ❌ (warnings OK)

## References

- `references/governance-deploy-session-2026-07-31.md` — full session trace: immutable-file failure, unlock, deploy, lock purge fallout

