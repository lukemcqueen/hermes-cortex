---
name: git-push-gate-failures
description: "Use when a push is blocked and the cause is unclear."
version: 1.0.0
author: Hermes Cortex
tags: [git, push, hooks, deploy, shell]
related_skills: [shared-repo-push-gates, enforcement-change-safety, shell-scripting]
---

# Git Push Gate Failures

Diagnosis patterns for blocked pushes in repos with the cortex governance
hooks (pre-push-pull, doctor gate, dogfood). Most rejections are
ENVIRONMENTAL — a stale deploy record, a hook false positive, or a shell
exit-code trap — not a problem with your diff. Diagnose the gate first;
your commit is usually fine.

## 1. "Deploy sync FAIL" that survives repeated cortex-update runs

**Symptom:** `cortex-doctor.py` shows `❌ Deploy sync` with "HEAD ahead of
last deploy" even after `cortex-update.sh` runs "cleanly" (rc 0 or rc 1
with a normal-looking log tail). The pre-push gate then blocks every push.

**Mechanism:** the doctor compares `git rev-parse HEAD` against
`~/.hermes-cortex/state/update-commit`, which cortex-update.sh writes near
the END of its run. If ANY earlier step dies under `set -euo pipefail`, the
record never advances. The log tail looks fine because the failing section
(service restarts) is adjacent to the end.

**Diagnosis (the tell):**

```bash
stat -c '%y' ~/.hermes-cortex/state/update-commit   # mtime BEFORE your changes?
```

An old mtime while deploys "run clean" = the deploy is dying before the
record write. Find the dying step: `bash -x ops/scripts/cortex-update.sh
--force` and read the trace around the last output. Fix that step, re-deploy,
and confirm the record advanced ("State saved: <hash>" + fresh mtime).
`rc` of a piped run (`bash script.sh | tail`) is NOT completion proof.

**Real root cause found this way (2026-09-01):** systemd ≥261 requires the
`.service` suffix in `systemctl list-unit-files <name>` — a bare name
returns EMPTY output/rc=1 even when the unit exists. cortex-update's
SERVICE_CTL scope-detection grepped `^${unit}` on a suffix-less query, the
check failed, it fell back to `systemctl --user`, and the dbus error
("Failed to connect to user scope bus") under `set -euo pipefail` killed the
deploy before `state/update-commit` was written. Fix: normalize the unit
name (`[[ "$unit" == *.* ]] || unit="${unit}.service"`) before querying.

## 2. First push to a brand-new remote is rejected

**Symptom:** `git push -u origin main` on a repo with an EMPTY remote fails
with "pre-push-pull: git fetch failed". The remote was just created via the
GitHub UI with no initial commit.

**Mechanism:** the pre-push hook runs `git fetch origin "$branch"`
unconditionally; on an empty remote the ref doesn't exist, fetch fails with
"couldn't find remote ref main", and the hook blocks the push — a false
positive (nothing to be behind; the no-verify gate already handles new
branches via remote_sha=0).

**Fixed hook behavior (2026-09-01):** the hook now discriminates with
`git ls-remote --exit-code origin "$branch"` captured as `|| LSRC=$?`:

```bash
LSRC=0
git ls-remote --exit-code origin "$branch" >/dev/null 2>&1 || LSRC=$?
if [[ $LSRC -eq 2 ]]; then
  : # ref absent → first push, allow (no-verify gate still checks new branches)
else
  exit 1   # ref present (0) or network/auth failure (≠2) → fail CLOSED
fi
```

⚠️ **FAIL-OPEN trap:** a bare `if git ls-remote ...; then block; fi` treats a
NETWORK failure (exit 128) the same as "ref absent" (exit 2) — a dead
remote pushes through. Only the exact `-eq 2` check fails closed.

**On a host with a pre-fix deployed hook:** create the remote ref manually
(first commit via GitHub UI, or push once from a non-hook context) so the
fetch succeeds, or deploy the hook fix first.

## 3. Exit-code-vs-output shell traps (set -euo pipefail)

Two commands return non-zero for EXPECTED results, silently killing scripts:

- `systemctl is-enabled <unit>` exits 1 when MASKED (prints "masked") — the
  desired state, not a failure.
- `git ls-remote --exit-code <remote> <ref>` exits 2 when the ref is absent
  — "no match" is the expected case.

**Trap A — `|| echo fallback` fires on EXIT CODE, not empty output:**

```bash
state="$(systemctl is-enabled hibernate.target 2>/dev/null || echo unknown)"
[[ "$state" == "masked" ]]  # FAILS — value is "masked\nunknown"

state="$(systemctl is-enabled hibernate.target 2>/dev/null || true)"
[[ "$state" == "masked" ]]  # works
```

**Trap B — standalone non-zero command kills the script before `$?`:**
capture in the `||`, initialize first, branch only on the exact code:

```bash
LSRC=0
git ls-remote --exit-code origin main >/dev/null 2>&1 || LSRC=$?
[[ $LSRC -eq 2 ]] && echo "absent"
```

## 4. Push blocked after rebasing over a peer's overlapping fix

**Symptom:** `git pull --rebase` succeeds (possibly after resolving a
conflict), but the push is then blocked by the dogfood gate: `❌ Deploy sync`,
`❌ Script content (<name>)`, `❌ Checksum: <file>.sh`. Your commit looks fine.

**Mechanism:** the dogfood gate diffs DEPLOYED scripts
(`~/.hermes-cortex/scripts/`) against repo HEAD. A peer's overlapping commit
changed the same script in the repo; your deployed copy still carries YOUR
pre-rebase version → checksum mismatch → gate blocks. The gate compares
deploy state, not your diff — your commit is not the problem.

**Fix:** re-run `bash ops/scripts/cortex-update.sh` (deploys the rebased repo
state, including the peer's version), verify the deployed file matches repo
(`diff <(grep -v '^# SOURCE:' ops/scripts/X.sh) <(grep -v '^# SOURCE:'
~/.hermes-cortex/scripts/X.sh)`), then push.

**Rebase conflict gotcha (2026-09-02):** during `git pull --rebase`, `--ours`
is the UPSTREAM (incoming, peer) version and `--theirs` is YOUR replayed
commit — the opposite of a merge. Taking `--theirs` on a conflict keeps YOUR
version, so your commit still carries a duplicate of a peer's identical fix.
To yield to the peer's already-pushed version, use `git checkout --ours
<file>` then `git add`; verify with `git show <sha> -- <file>` (should be
empty for the duplicated file) before amending. Prefer the peer's version
when it is identical-or-better and already public.

## Verification checklist

- [ ] `stat` the update-commit mtime before debugging your diff
- [ ] `bash -x` the deploy to find the dying step (don't trust the log tail)
- [ ] Test the hook with a 4-case scratch matrix: first push → ALLOW;
      normal push → PASS; fetch fails + ref exists → BLOCK; remote
      unreachable → BLOCK
- [ ] A4 adversarial gate on hook/deploy changes before commit

## Public-repo publishing discipline (user preference, 2026-09-01)

When creating a PUBLIC repo (e.g. the omarchy-omar project), the user's hard
rule: **zero PII — no real usernames, hostnames, LAN/WAN IPs, domains,
phone/email, bot or session identifiers, machine serials.** Public repos are
crawled; a leaked identifier is permanent. Practice:

- Use placeholders everywhere: `YOURUSER`, `192.168.1.x`, `example.com`,
  `mymac`. Configs are templates for strangers to copy, never live values.
- Before pushing, grep the whole tree:
  `grep -rniE '192\.168|1270130526|<realhost>|<realdomain>' .` → clean.
- Audit doc cross-references resolve (`](path)` from each file's own dir);
  broken links fail the repo's own QA.
- Scripts ship with a `--check` mode and pass `bash -n` before commit.

## Related

- `references/fine-grained-pat-capabilities.md` — fine-grained GitHub PAT
  format, create/push permission gaps (Administration vs Contents), and the
  browser-created-repo unblock.
- `shared-repo-push-gates` (sibling) — gate catalog + concurrent-session
  discipline; this skill is the diagnosis playbook for when a gate blocks.
