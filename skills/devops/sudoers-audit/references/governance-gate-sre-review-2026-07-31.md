# Governance-Gate SRE Review — hermes-plugin-lock unlock gate (2026-07-31)

Case study: an SRE/Domain/QA review of a draft design to make `cortex-update.sh` the ONLY
mechanism that updates the immutable enforcement chain (enforcer plugin, pre-commit hook
scripts, loop-gov-mcp.py), with an orchestrator-only manual exception.

## The draft design under review

- `hermes-plugin-lock` gates `unlock`/`update` on `CORTEX_UPDATE=1` OR `AGENT_ID=moses|esther`
  (`lock` and `status` stay open). Callers must use `sudo CORTEX_UPDATE=1 hermes-plugin-lock unlock`
  because sudoers has env_reset.
- `cortex-update.sh` exports `CORTEX_UPDATE=1` and passes it explicitly through sudo.
- Pre-commit DOGFOOD (auto-deploy enforcer on drift) to become a BLOCK instructing cortex-update.
- Doctor remediation hints to be re-pointed to cortex-update.

## Findings (severity-ranked, all live-verified)

1. **P0 — `sudo VAR=val cmd` fails under command-specific NOPASSWD + env_reset without SETENV:**
   `sudo -n CORTEX_UPDATE=1 /usr/local/sbin/hermes-plugin-lock unlock` → "sudo: a password is
   required" even though the bare-path rule exists. Every sudo unlock call in cortex-update.sh
   (copy_file ~L613, check_each_mapped_file ~L710/712, deploy_governance_plugin ~L1341) uses this
   form and wraps it in `2>/dev/null || true` → the sanctioned channel silently no-ops → the
   subsequent `cp` fails against `chattr +i` → the enforcement deploy breaks while appearing fine.
   Fix: `SETENV:` tag on the rule, or a root-owned marker file (`/run/<name>-ok`) instead of env.
   Full pitfall + detection in the parent SKILL.md.

2. **P0 — ambient env vars make caller gates fire on the wrong side:** `AGENT_ID=moses` is exported
   in every shell on this fleet (AGENTS.md rule 20). A "non-orchestrator, no env" invocation of the
   gated helper PASSED the orchestrator branch — the refusal test never fired for the case the gate
   was built for. Fix: bind the exception to `SUDO_USER` against a root-owned allowlist
   (`/etc/<name>-orchestrators`), not env vars.

3. **P0 — gating the helper's own `update` bricks upgrades permanently:** the deployed helper is
   `chattr +i`; `update` (unlock self → cat repo source → relock) is the ONLY refresh mechanism
   (the `sudo cp` fallback fails against the immutable self). Gating `update` = the helper updates
   exactly once (to the gate-introducing version) and can never be upgraded again. `update` only
   rewrites the helper itself, never the enforcement TARGETS — leave it ungated.

4. **P1 — DOGFOOD→BLOCK is NOT a deadlock, but only if the sanctioned channel works:** the block
   is recoverable because (a) repo sources are not immutable (agent can always run cortex-update.sh
   from the repo), and (b) cortex-update.sh does not require a governance lock — the committing
   agent already holds one. It BECOMES a deadlock if the sanctioned channel is broken (finding 1).
   The blocked agent must also reload the 8 always-skills and re-`begin_change()` after the update
   (cortex-update's purge loop deletes its active `.governance-*.json` lock and re-deploying the
   enforcer invalidates `.skills-loaded`) — document this in the BLOCK message.

5. **P1 — ship the gate and the DOGFOOD→BLOCK conversion in the same commit:** with the gate live
   and DOGFOOD still auto-deploying, `sudo hermes-plugin-lock unlock` is REFUSED, `|| true` swallows
   it, `cp` fails silently, the commit proceeds with a drifted enforcer, and the "✅ Auto-deployed"
   line is a lie. Convert DOGFOOD to a hard `exit 1` block in the same change.

6. **P1 — doctor remediation hints teach the refused command:** checks.py ~L1617-1625 (`cp
   pre-commit-score → hooks/pre-commit`) and ~L1528-1532 (`rm -rf + ln -sf` enforcer symlink) fail
   against `chattr +i` files even WITHOUT the gate. Re-point all to
   `bash ~/hermes-cortex/ops/scripts/cortex-update.sh --force-all`. The `Immutable` (lsattr) and
   `Plugin lock helper` (`sudo -n … status`, bare path) checks are unaffected by gating.

7. **P1 — docs/skills teach the refused command:** `governance-plugin-implementation.md` and
   `plugin-lock-helper-doctor-check.md` show manual `sudo hermes-plugin-lock unlock` — update in
   the same commit (docs-not-optional rule).

## Clean surfaces (verified, no change needed)

- Auto-remediation pipeline (agent-remediation-sensor, agent-remediate-apply, agent-fixer crons,
  agent-governance-auditor) has ZERO direct writes to enforcement paths; the auditor is read-only
  and excludes `.hermes*` dirs.
- Only callers of `hermes-plugin-lock` in the whole repo: cortex-update.sh, pre-commit-score
  (DOGFOOD), cortex_doctor/checks.py, and docs/skills. Blast radius = exactly the intended surface.
- `agent-hermes-cortex-sync.sh` pulls the repo but does NOT run cortex-update (no gate impact).

## QA test matrix required before shipping

1. Adversarial: `env -u AGENT_ID -u CORTEX_UPDATE bash <repo-helper> unlock` → REFUSED, exit 1,
   `lsattr` unchanged before/after.
2. Non-orch spoof rejected (post-fix 2): `AGENT_ID=worker` refused; orchestrator allowed only via
   the Unix-account mechanism.
3. Sanctioned: `CORTEX_UPDATE=1 bash <repo-helper> unlock` gate passes (non-sudo run of the repo
   copy is the CI-safe way to exercise the gate — chattr fails harmlessly as the unprivileged user).
4. Orchestrator channel: `sudo AGENT_ID=moses hermes-plugin-lock unlock` passes (if env kept).
5. Ungated ops: `lock` and `status` work with no env.
6. DOGFOOD block: drifted hash → block message points at cortex-update.sh, exit non-zero;
   retry-after-update completes (skills reload + re-begin_change).
7. Doctor regression: `Immutable:*` PASS, `Plugin lock helper` PASS, no `cp`-style hints remain.
8. Self-update: `sudo -n /usr/local/sbin/hermes-plugin-lock update` succeeds (post-fix 3).
9. E2E: cortex-update.sh run → deployed enforcer hash == repo hash, `+i` on all TARGETS.

## Live host facts (moses box, 2026-07-31)

- sudoers: `env_reset, secure_path, use_pty, pwfeedback`; `(ALL : ALL) ALL` for moses (full sudo —
  gate is an accident-prevention interlock here, not a security boundary); command-specific
  `(root) NOPASSWD: /usr/local/sbin/hermes-plugin-lock` — NO SETENV: tag.
- `/usr/local/sbin/hermes-plugin-lock`, `~/.hermes-cortex/scripts/hermes-plugin-lock`, enforcer
  `__init__.py`, `pre-commit-score`, `loop-gov-mcp.py` all `chattr +i`.
- Gate behavior live-tested with the repo copy: `AGENT_ID=worker` → REFUSED (exit 1); ambient
  `AGENT_ID=moses` → gate passed; `status`/`lock` ungated.
- `sudo -n CORTEX_UPDATE=1 /usr/bin/env` → "sudo: a password is required" (finding 1 reproduced).
