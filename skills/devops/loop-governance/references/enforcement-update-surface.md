# Enforcement Update Surface Audit (2026-07-31)

Goal (owner directive): **cortex-update.sh must be the ONLY mechanism that updates the
locked enforcement files**, with a narrow orchestrator-only (AGENT_ID=moses|esther)
manual exception. Non-orchestrator agents must have ZERO direct update/unlock capability.

## Files in the immutable chain (hermes-plugin-lock TARGETS)

- `~/.hermes/plugins/governance-enforcer/__init__.py` (chmod 444 + chattr +i)
- `~/.hermes-cortex/scripts/pre-commit-score`, `pre-push-pull`, `post-commit-audit`,
  `post-push-audit`
- `~/.hermes-cortex/hooks/post-merge`
- `~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py`
- `hermes-plugin-lock` itself (self-protection)

## Complete write-path inventory

| # | Path | Writes? | Verdict |
|---|------|---------|---------|
| 1 | `cortex-update.sh` — `deploy_governance_plugin()` (~1310), hooks install (~1334), `register()` | Yes | ✅ Sanctioned path — KEEP. Must pass `CORTEX_UPDATE=1` through sudo |
| 2 | `ops/scripts/pre-commit-score` lines 73–88 DOGFOOD self-heal: `sudo hermes-plugin-lock unlock; cp -f repo deployed; lock` | Yes | ⚠️ **SECOND CHANNEL** — convert to a BLOCK that instructs running `cortex-update.sh` (auto-deploying the enforcer on commit bypasses the sanctioned path entirely) |
| 3 | `ops/install/deploy/nginx/hermes-plugin-lock` — `unlock`/`update` subcommands | Yes | ⚠️ **Direct write channel** — gate on `CORTEX_UPDATE=1` OR orchestrator `AGENT_ID=moses|esther`; `lock`/`status` stay open |
| 4 | `ops/scripts/cortex_doctor/checks.py` ~1617–1624 remediation hints: `cp pre-commit-score → hooks/pre-commit` | Instructs agents to | ⚠️ Bypass instruction — re-point to `cortex-update.sh` |
| 5 | `ops/install/install.sh` — one-time bootstrap (root, fresh install) | Yes | ✅ Legitimate exemption (bootstrap) |
| 6 | `ops/scripts/manage/cortex_doctor/fix.py` ~251 — `sudo chattr +i` only | Lock direction only | ✅ Safe (never unlocks) |
| 7 | `ops/scripts/manage/agent-governance-auditor.py` — suggests `sudo chattr +i` | Lock direction only | ✅ Safe |

## Critical platform details

- **sudoers env_reset**: environment variables do NOT survive plain `sudo cmd`. Callers
  must use explicit assignment syntax: `sudo CORTEX_UPDATE=1 hermes-plugin-lock unlock`.
  A bare `export CORTEX_UPDATE=1` in the parent shell is stripped by sudo.
- **Linux enforcement anchor**: `moses ALL=(ALL) ALL` (password) + NOPASSWD entries
  including `/usr/local/sbin/hermes-plugin-lock`. Everything else needs a password agents
  lack — the NOPASSWD hermes-plugin-lock entry IS the whole unlock surface on Linux.
- **macOS**: `chflags uchg` needs no root (user owns the files) — enforcement is weaker
  by design; script-level gating (`_require_sanctioned_caller`) is the only lever there.
- **Long-lived LLM crons** (`agent-bus-workday` style) auto-acquire governance locks via
  the loop-gov MCP and can trigger purge loops; see `lock-lifecycle-race.md`.

## Sanctioned-caller gate design (draft under party review)

`_require_sanctioned_caller <op>` in hermes-plugin-lock:
```bash
if [[ "${CORTEX_UPDATE:-0}" == "1" ]]; then return 0; fi
case "${AGENT_ID:-}" in moses|esther) return 0 ;; esac
# else: refuse with actionable message pointing at cortex-update.sh
```
Refusal message must name the exact correct path (cortex-update.sh) — never just "denied".
