---
title: sudoers-audit
name: sudoers-audit
version: 1.0.0
description: Systematically audit, test, and debug sudoers NOPASSWD rules — verify allowed commands actually run without password, diagnose silent rule failures, and fix common pitfalls.
category: devops
triggers:
  - user asks to check sudoers, test sudo, verify NOPASSWD, fix sudo permission
  - a sudo -n command unexpectedly asks for password
  - setting up new sudoers rules
  - diagnosing 'a password is required' errors on NOPASSWD entries
---

# sudoers-audit

Systematic approach to auditing, testing, and debugging sudoers NOPASSWD rules.

## Platform Notes

This skill covers **Linux** (primary) and **macOS** (noted where different).

| Aspect | Linux | macOS |
|--------|-------|-------|
| Sudoers directory | `/etc/sudoers.d/` | `/etc/sudoers.d/` (supported) |
| Auth log | `/var/log/auth.log` | `log show --predicate 'process == "sudo"'` or `/var/log/system.log` |
| File permissions | `r--r-----` root:root | Same convention |
| NOPASSWD syntax | `ALL=(root) NOPASSWD:` | Same syntax |
| `sudo -n` support | Yes | Yes |

All audit procedures (list rules, test NOPASSWD, verify paths) work the same
on both platforms unless noted. The auth.log diagnostic step uses a different
path on macOS.

## Why rules fail silently

A sudoers rule that `sudo -n -l` shows as valid can still fail at execution time due to:
- **Path mismatch**: the rule specifies `/usr/bin/apt` but `which apt` resolves to `/usr/local/bin/apt`
- **Wrapper scripts**: Mint's `/usr/local/bin/apt` shadows the real binary, and its internal `sudo`-prepending logic can create infinite loops or unexpected behavior
- **Permission mismatch**: sudoers files are `r--r-----` owned by root — `moses` cannot `cat` or `stat` them, only `sudo -n -l` reveals content
- **Duplicate/conflicting entries**: rules in multiple include files can create conflicts where one works and another doesn't
- **Argument sensitivity**: `systemctl status nginx` is NOT covered by a rule allowing `systemctl reload|start|stop|restart nginx`
- **apt vs apt-get**: a rule for `/usr/bin/apt` does NOT apply to `/usr/bin/apt-get`
- **Env-prefixed commands**: `sudo -n FOO=1 cmd` does NOT match a rule for bare `cmd` (see next section — this is a design-breaking silent failure)

## Env-assignment through sudo: `sudo VAR=val cmd` vs command-specific NOPASSWD

**Symptom (live-verified 2026-07-31):** `sudo -n CORTEX_UPDATE=1 /usr/local/sbin/helper` → `sudo: a password is required`, even though `sudo -n -l` shows `(root) NOPASSWD: /usr/local/sbin/helper` and the bare `sudo -n /usr/local/sbin/helper` runs fine.

**Cause:** a command-specific sudoers entry matches the bare command path. The `VAR=val` prefix makes the effective command different (`CORTEX_UPDATE=1 /usr/local/sbin/helper` ≠ `/usr/local/sbin/helper`), so no NOPASSWD rule matches and sudo falls back to password auth. `env_reset` strips the *inherited* environment but does NOT grant the right to *assign* variables on the sudo command line — that requires the `SETENV:` tag. (Plain `env_keep` is a different, broader lever.)

**Detect:**
```bash
sudo -n FOO=1 /usr/bin/env 2>&1 | grep FOO   # empty + "a password is required" = the prefix broke the match
sudo -n -l /usr/local/sbin/helper            # bare rule present, but that's not what the caller runs
```

**Fix options:**
1. Add the `SETENV:` tag to the rule (narrowest): `(root) NOPASSWD: SETENV: /usr/local/sbin/helper` → `sudo -n FOO=1 helper` then works. Validate with `sudo /usr/sbin/visudo -c` and re-test `sudo -n FOO=1 /usr/bin/env`.
2. Avoid env-passing entirely: the caller drops a root-owned marker file (e.g. `/run/<name>-ok`) before the sudo call; the helper checks it under `SUDO_USER`. Works with plain bare-path rules, no sudoers change.
3. If the helper runs under an interpreter (`sudo -n bash helper`), the rule must name interpreter+path exactly — a `VAR=val` prefix still breaks the match.

**Design rule:** never build a call flow around `sudo VAR=val cmd` without verifying the sudoers rule carries `SETENV:`. Test it live before writing the design; don't trust "env_reset + explicit assignment should work". A gate that only *appears* sanctioned (unlock silently refused, `2>/dev/null || true` swallows it) is worse than no gate.

## Caller-gating privileged helpers: env-var checks are spoofable

A gate like `[[ "$AGENT_ID" == moses|esther ]]` inside a helper is NOT an identity boundary when the var is ambient. On this fleet `AGENT_ID=moses` is exported in every shell (AGENTS.md rule 20), so a "no env" invocation of a gated helper still passes its orchestrator gate by default — live-verified: the refusal test passed because the ambient shell env carried `AGENT_ID=moses`. Any process can also set the var itself.

- **Real boundary:** the helper runs as root via NOPASSWD with `SUDO_USER` set — compare `SUDO_USER` against a root-owned allowlist file (e.g. `/etc/<name>-orchestrators` created by install.sh), or use the root-owned marker-file pattern above. Never trust caller-controlled env vars for access control.
- **Env-var gates are still useful** as accident-prevention interlocks (stop *unaware* writes, keep `lock`/`status` open, refuse plain `unlock`). Say so in the design; don't market them as security.
- **Never gate the helper's own self-update path** (`helper update` / self-deploy): the deployed helper is typically `chattr +i`, so its own `update` (unlock self → cat repo source → relock) is the ONLY refresh mechanism — the `sudo cp` fallback also fails against the immutable self. Gating it means one-time update then permanent staleness. It only rewrites itself, never the enforcement targets, so it adds no security.
- **Testing gate logic without root:** run the REPO copy of the helper as the unprivileged user — the gate branch (refuse vs proceed) is fully exercised, and the chattr operations fail harmlessly ("Operation not permitted") with no state change. Verify with `lsattr` before/after. This makes gate behavior testable in CI without sudo.

> **Case study:** `references/governance-gate-sre-review-2026-07-31.md` — full SRE review of gating a chattr-based enforcement helper (`hermes-plugin-lock`): the DOGFOOD→BLOCK transition, deadlock analysis, doctor-hint re-pointing, and the QA test matrix.

## Audit procedure

### 1. List all rules for the current user
```bash
sudo -n -l
```
Output shows all NOPASSWD and PASSWD rules. Note the order — later rules override earlier ones for the same command.

### 2. Test if a specific command is *allowed by policy*
```bash
sudo -n -l /usr/bin/apt clean
# Exit 0 = allowed, exit non-zero = not matched by any rule
```
This tests whether sudo *parses* a matching rule — it does NOT test whether NOPASSWD works at runtime.

### 3. Test actual NOPASSWD execution
```bash
sudo -n /usr/bin/apt clean
# Exit 0 + no prompt = NOPASSWD works
# "a password is required" = rule exists but NOPASSWD tag isn't applying
```
Use `-n` (non-interactive) to force sudo to fail fast if it would need a password.

### 4. Diagnose failures in auth.log
```bash
# Linux
tail /var/log/auth.log

# macOS
log show --predicate 'process == "sudo"' --last 1h | grep -E "session|password|NOPASSWD"
```
Patterns to look for:
- `a password is required` — sudo reached a PASSWD rule for this command
- Missing `pam_unix(sudo:session): session opened` — NOPASSWD didn't fire
- Entry WITHOUT `a password is required` + session opened/closed = NOPASSWD worked

### 5. Verify binary paths
```bash
which apt                    # Actual resolved path on PATH
file /usr/local/bin/apt      # Check for wrapper scripts
head -5 /usr/local/bin/apt   # Inspect wrapper logic
```
The `which` path may differ from the path in the sudoers rule — this is the #1 cause of silent failures.

### 6. Identify sudoers file structure
```bash
ls -la /etc/sudoers.d/       # List include files (names + sizes)
```
Files are `r--r-----` owned by root and not readable by non-root. Use `sudo -n -l` output to infer content. File sizes help identify single-rule files vs multi-rule files.

## Common pitfalls

- **Mint `apt` wrapper** at `/usr/local/bin/apt` shadows `/usr/bin/apt`. When run as non-root, it prepends `sudo` to the real command internally — this recursive sudo can interact badly with NOPASSWD rules.
- **`systemctl status`** is a read-only command but rarely included in NOPASSWD rules. Add it explicitly: `(ALL) NOPASSWD: /usr/bin/systemctl status nginx`
- **Duplicate rules** from multiple include files can cause confusion. Check if `sudo -n -l` shows the same rule twice.
- **Cmnd_Alias conflict**: a catch-all `(ALL : ALL) ALL` rule (PASSWD by default) listed before NOPASSWD rules is fine — sudo uses last-match-wins. But if it appears AFTER, it overrides all NOPASSWD tags.
- **Arguments matter**: `/usr/bin/apt autoremove` matches `apt autoremove` but adding flags like `--dry-run` should still match (sudo matches the first argument). If flags break the match, check sudoers grammar version compatibility.
- **Reading sudoers files**: cannot `cat`/`stat` them as non-root. Use `sudo -n -l` for content discovery. To diagnose parse errors, run `sudo /usr/sbin/visudo -c` in an interactive terminal (not via `-n`).

## Test matrix template

| Command | `sudo -n -l` says | `sudo -n` runs | Auth log evidence |
|---|---|---|---|
| `nginx -t` | Allowed ✅ | Works ✅ | Session opened |
| `apt clean` | Allowed ✅ | Works ✅ | Session opened |
| `apt autoremove` | Allowed ✅ | Password req ❌ | "a password is required" |
| `systemctl status nginx` | Not listed ❌ | Fails ❌ | Expected |

## Creating NOPASSWD rules for a new service

### Scoping rule: enumerate the minimum subcommand, not the whole binary

When adding a NOPASSWD rule for a firewall/nft/iptables command used by
the security-posture-check or similar health checks, **scope to the exact
subcommand and arg pattern** — never a bare `ALL=(root) NOPASSWD: /usr/sbin/nft`
that grants full root access to the entire nft toolchain (including table
create/delete, flush rules, etc.).

**Correct (read-only list set):**
```
ALL=(root) NOPASSWD: /usr/sbin/nft list set *
ALL=(root) NOPASSWD: /usr/sbin/iptables -L f2b-*
ALL=(root) NOPASSWD: /usr/sbin/iptables-save
```

This lets esther/moses enumerate the f2b ban set to verify it exists, but
NOT create/delete/modify nft tables or iptables chains. Same principle
applies to any sudoers rule: the command-name argument list is a security
boundary — use it.

**Always test the arg pattern:**
```bash
sudo -n nft list set inet f2b-table addr-set f2b-sshd >/dev/null && echo "OK" || echo "FAIL"
```
The `*` wildcard in sudoers matches per-word, so `nft list set *` matches
any args following `list set`.

**Living document:** the `agent-security-posture-check.sh` script in
`ops/scripts/` has the canonical list of nft/iptables invocations it
requires — regenerate the sudoers rule from its source of truth.

### Legacy approach: individual command rules

### Preferred approach: refactor broad scripts into tight single-path rules

When an existing NOPASSWD rule grants access to a **script** (e.g. `hermes-security-apply`) that can do many things as root, replace the script with a **focused replacement** that needs only one tight `sudo cp` rule.

**Pattern:**
1. Identify what the script ACTUALLY needs root for (survey all callers, check every command it runs)
2. Create a replacement that does the root-requiring part in one deterministic step (e.g. `sudo cp /tmp/generated.conf /etc/nginx/blocked_ips.conf`)
3. Do everything else (config generation, validation) as non-root
4. Replace the old NOPASSWD script rule with just the tight `cp` rule

**Real example: hermes-security-apply → deploy-blocked-ips.sh**

| Before | After |
|--------|-------|
| NOPASSWD for `/usr/local/sbin/hermes-security-apply` (can write any nginx config, fail2ban, reload services) | NOPASSWD for `/bin/cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf` (ONE file, ONE destination) |
| Scripted backup, zone-defs deploy, services config, fail2ban filter, nginx reload | `fix-blocked-ips.py` generates config (no root) → `sudo cp` (tight path) → `sudo nginx -t` (existing) → `sudo nginx -s reload` (existing) |

**Benefits:**
- Eliminates entire attack surface of the old script
- `sudo cp` is a single atomic operation — no scripted logic that could misbehave
- The generated config is validated by `nginx -t` before reload
- Audit trail: the cp rule specifies exact source AND destination paths
- Other agents can adopt the same pattern for their own broad scripts

## Verification checklist

- [ ] Each NOPASSWD rule passes `sudo -n -l <command>` (allowed by policy)
- [ ] Each NOPASSWD rule passes `sudo -n <command>` (actually runs without password)
- [ ] Auth log confirms session opened/closed (NOPASSWD) not "password required"
- [ ] Binary paths in rules match `which` resolution
- [ ] No wrapper scripts shadow real binaries at unexpected paths
- [ ] Read-only commands (`status`, `-t`, `--dry-run`) are included if needed
- [ ] Rules are not duplicated across include files unless intentional