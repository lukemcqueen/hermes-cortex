# Hermes Forensic Evidence Sources — Worked Example

Exact evidence locations and the 2026-08-01 investigation that proved the
`agent-hermes-cortex-sync` cron was NOT the deleter of 10 security files.

## Evidence paths (Hermes on moses host)

| Evidence | Path | What it tells you |
|----------|------|-------------------|
| Cron run output | `~/.hermes/cron/output/<job_id>/<timestamp>.md` | stdout of every no_agent cron run — the script's own log of what it did |
| Cron job registry | `~/.hermes/cron/jobs.json` | map job_id → name, schedule, script, no_agent flag |
| Cron execution DB | `~/.hermes/cron/executions.db` (table `executions`) | job_id, source, status, started_at, finished_at per run |
| Session store | `~/.hermes/state.db` (tables `sessions`, `messages`) | every agent session + every tool call with args |
| Enforcement audit | `/var/log/hermes-enforcement.log` | unlock/lock events (ACCEPTED/REFUSED + token used) |
| Enforcement immutability | `lsattr <file>` | `----i---------e-------` = chattr +i locked |
| User shell history | `~/.zsh_history`, `~/.bash_history` | interactive commands (flush caveats, see below) |

## state.db schema notes

- `messages` table columns of interest: `id, session_id, role, content,
  tool_calls, timestamp`. The `tool_calls` column is a JSON **array** of
  `{type: "function", function: {name, arguments}}`; `arguments` is a
  **JSON-escaped string** — parse with `json.loads` twice (outer array, then
  the arguments string). Regex on the raw column misses escaped quotes.
- `sessions` table: `id, source (cli|telegram|cron|subagent), title,
  started_at, ended_at, message_count, tool_call_count`. `ended_at=NULL`
  means still-open or a stub. Subagent sessions have their own IDs and
  `source='subagent'` — check them separately or you'll miss tool calls.
- Empty telegram sessions (0 messages) are connection stubs, not actors.
- Epoch timestamps: `datetime.datetime.fromtimestamp(ts)` for readability.

## Worked example — 2026-08-01 hermes-plugin-lock deletion

Symptom: `git status` showed 10 unstaged deletions of security files
(`ops/install/deploy/nginx/hermes-plugin-lock`, `blocked_ips.add`,
`hermes-security`, `deploy-sudoers.sh`, `fix-blocked-ips.py`,
`deploy-fix-blocked-ips.sh`, `MOSES.md`, `ops/offline/SKILL.md`,
`ops/README.md`, `clickhouse-config.d/02-low-memory.xml`).

Chain of proof (each step ruled out one suspect):

1. **Uncommitted ≠ remote**: `git ls-files --deleted` → all 10 still tracked
   in index; `git log --oneline -1 origin/main` confirmed remote safe.
2. **Reflog timing**: `git reflog --date=iso` showed `45fad864 reset: moving
   to HEAD` at 22:33:27 — exactly 1s before the nginx dir mtime 22:33:28.
   That is the `git stash push` internal reset, not a deletion.
3. **Stash inspection**: the cron's stash commit (`19e25efc...`, still
   reachable after "Dropped refs/stash@{0}") had parent = HEAD at stash time
   and contained the 10 deletions → they existed BEFORE 22:33:27.
4. **Cron output**: `~/.hermes/cron/output/462eb6bd42a6/2026-08-01_22-33-28.md`
   = `agent-hermes-cortex-sync` (script stashes → fetches → pops). Its
   `deleted:` lines are the pre-existing state it saved and restored.
5. **Session sweep**: queried state.db `tool_calls` for ALL terminal
   commands 21:00–22:35 across all sessions → zero rm/git-rm/checkout/clean
   on those paths. Every session's commands were read-only diagnostics.
6. **Backup window**: the 21:03 git bundle (`repos/hermes-cortex-public.bundle`)
   contained all 10 files (`git cat-file -e FETCH_HEAD:<path>` PRESENT) →
   deletion happened between 21:03 (bundle) and 22:33:27 (stash).
7. **Shell caveat**: zsh history showed no rm, BUT the user rebooted 4× in
   the window (21:33/21:40/22:02/22:50) — each reboot kills the shell before
   history flush, so the user's shell is neither exonerated nor convicted.
   Reported the gap honestly instead of claiming innocence.
8. **SSH check**: `who` + `ss -tnp | grep :22` → exactly 1 SSH session (the
   user's); lightdm local console is not SSH; one preauth bot probe rejected.
   No second human/agent via SSH.

Verdict delivered: the cron preserved, did not create, the deletion; the
true deleter was never positively identified, but the security-critical
files were never committed — remote safe, working tree restorable.

## Verified-innocent cron pattern

`agent-hermes-cortex-sync.sh` (no_agent, daily 22:33 KST):
```
if ! git diff --quiet || ! git diff --cached --quiet; then
    git stash push -m "auto-stash before cortex-sync ..."
    STASHED=true
fi
git fetch origin
# if HEAD..origin/main empty → stash_pop && exit 0
GIT_EDITOR=true timeout 20 git pull --rebase origin main
stash_pop   # git stash pop → "Dropped refs/stash@{0}"
```
Any "deleted:" line in its output = working-tree state that already existed
before the run. The stash commit SHA is printed in the output — capture it
for `git show --stat`.

## Related red herrings seen in practice

- Hardline blocklist error at 21:49 was a `grep -c "hc.e2fsck_fcc"` command
  with regex chars the parser rejected — not a deletion attempt. Always read
  the assistant message immediately before the block.
- `search_files` returned 0 for `.hermes`/`.hermes-cortex` paths that
  demonstrably exist — ripgrep skips hidden dirs. Use `ls`/`find`/`git
  ls-files` to confirm absence.
- The `.hermes-cortex/.governance-lock` file inside the repo (a cron
  session's lock) is untracked and unrelated to working-tree deletions —
  don't chase it as a deletion suspect.
