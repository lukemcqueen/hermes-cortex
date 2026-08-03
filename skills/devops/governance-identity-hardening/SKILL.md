---
name: governance-identity-hardening
description: "Use when hardening orchestrator identity or unlock tokens."
version: 1.0.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, identity, spoofing, orchestrator, git-authorship, enforcer, pre-commit]
    related_skills: [enforcer-modification-considerations, cortex-preflight, two-hard-rules, shell-scripting]
---

# Governance Identity Hardening

**Class of work:** closing spoof holes in the governance/enforcement chain —
who is allowed to do orchestrator-only things, and how commits are attributed.

## When to Use

- Any `AGENT_ID` / `AGENT_TYPE` / `IS_ORCHESTRATOR` env var gates orch powers
- Commit authorship is showing a human identity for agent-originated commits
- An unlock/update token is accepted without verifying the caller
- An LLM fixer cron or agent claims orchestrator identity it shouldn't have

## Core Principle: Host-Derived Identity, Never Env

Env vars are **claims, not proof**. An LLM fixer cron told "You are Moses, the
orchestrator" will happily set `AGENT_ID=moses` and push to orchestrator-only
paths — this actually happened (a non-orch host pushed to `ops/scripts/`).

Orchestrator = **two independent host signals, checked together**:

```bash
_detect_orch() {
  local _host _home _user
  _host=$(hostname -s 2>/dev/null || echo "unknown")
  _user=$(id -un 2>/dev/null || echo "$USER")
  _home=$(getent passwd "$_user" 2>/dev/null | cut -d: -f6)
  _home="${_home:-$HOME}"
  case "$_host" in
    moses|esther)
      [[ "$_home" == "/home/$_host" ]] && return 0
      ;;
  esac
  return 1
}
```

Orch hosts have hostname == agent name == home dir (`esther`→`/home/esther`).
Non-orch hosts have hardware hostnames and shared `/home/luke` — neither
signal alone is sufficient.

## Where to Apply (every place that grants orch powers)

| File | Gate |
|------|------|
| `pre-commit-score` | DOGFOOD block, orchestrator-only paths guard, ORCHESTRATOR_ONLY_PATHS block, self-test |
| `cortex-update.sh` | ORCH_MAP merge (~725), ORCH_MAP protect (~795), orch-cron install (~1900) |
| `os-config.sh` | `CORTEX_AGENT_TYPE` detection (shared — propagates via `check_agent_type`) |
| doctor `config.py` | hostname fallback (already correct for orch hosts) |

**Missed-gate check:** after patching the hook, grep for the same env-var
pattern across the whole tree — `grep -rn "IS_ORCHESTRATOR\|AGENT_TYPE.*orchestrator" ops/scripts/` — the same spoof hole usually exists in 3-5 sibling locations (install-orch-crons.sh, os-config.sh, multiple cortex-update.sh gates).

## Impersonation Watchtower

When a claimed identity contradicts the host signals, write a LOUD line to a
state file delivered by a no_agent watchdog (never block on network in a hook):

```bash
ALERT_FILE="${HOME}/.hermes-cortex/state/impersonation-alerts.log"
_log_impersonation() {
  local claimed="${1:-unknown}"
  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] IMPERSONATION: ${claimed} claimed on host $(hostname -s 2>/dev/null) — non-orchestrator host cannot be moses/esther"; } \
    >> "$ALERT_FILE" 2>/dev/null || true
}
```

The pre-commit hook writes the alert file; a separate no_agent cron (1-5 min)
delivers new lines to Telegram. This matches the existing
`agent-governance-auditor` delivery pattern.

## Git Authorship: agent.env + Deploy-Time Config

**Constraint:** a pre-commit hook runs as a child of `git commit` and CANNOT
set the author of the commit being created (child→parent env doesn't
propagate). Identity must be set at deploy time; the hook only verifies.

Pattern:
1. `~/.hermes-cortex/agent.env` holds `AGENT_NAME=<agent>` — **gitignored**,
   per-host (each machine's `/home/<user>` is a separate physical box, so the
   file is distinct even though the home path string is shared).
2. `cortex-update.sh` calls `ensure_agent_identity()` (in os-config.sh) which
   reads agent.env; orch hosts derive AGENT_NAME from hostname and write it;
   non-orch hosts must provision it once.
3. cortex-update.sh sets `git config user.name "AGENT_NAME-agent"` /
   `user.email "AGENT_NAME@hermes.local"` — commits now carry the agent.
4. pre-commit hook verifies agent.env exists (fails closed with setup
   instructions) and AGENT_NAME matches hostname on orch hosts.

**PII rule:** the hostname→agent mapping is infrastructure. It must NEVER be
committed to the public repo — provision agent.env per machine instead.

## Spoofable Unlock Tokens

`hermes-plugin-lock unlock --cortex-update` historically accepted the token
from ANY account with zero caller proof. The token was a string, not a caller.

Fix pattern: **fresh root-owned marker file** created inside cortex-update.sh
immediately before unlocking; the helper requires the marker to exist, be
root-owned, and be <60s old. `--orchestrator` stays account-bound
(SUDO_USER/USER must be moses|esther — an account boundary, not an env var).

## Pitfalls

- **Piped git pull masks failure:** `git pull ... | tail && git commit`
  continues after a FAILED pull because `&&` sees the pipe's last command
  (tail) exit 0. Capture pull status separately or verify
  `git status -sb` shows no ahead/behind before committing.
- **Rebase bypasses hooks:** `git pull --rebase` replays commits without the
  pre-commit hook; the pre-push hook then flags them. Fix: amend the commit
  through the hook (`git commit --amend --no-edit`) before pushing.
- **Self-test must match the new logic:** when changing identity checks,
  rewrite the hook's self-test (e.g. "AGENT_ID controls orchestrator
  identity") to assert the hostname+home-dir behavior and env-independence —
  a stale self-test fails every commit.
- **Deploy ordering:** cortex-update.sh sources os-config.sh at runtime; on
  the FIRST run after a fix it sources the OLD deployed copy. Re-run the
  deploy once to confirm the identity line self-heals.

## Verification Checklist

- [ ] `bash -n` all touched shell files
- [ ] `_detect_orch` returns 0 on this host if orch; simulated non-orch host stays blocked
- [ ] Env spoof test: `AGENT_ID=moses` on a non-orch host changes nothing
- [ ] grep for residual `IS_ORCHESTRATOR` / `AGENT_TYPE` orch grants in sibling files
- [ ] Deployed copies carry the new check (not just repo source)
- [ ] Pre-commit self-test passes on the deployed hook
- [ ] Agent commits show `AGENT_NAME-agent <AGENT_NAME@hermes.local>`, not the human
