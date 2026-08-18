---
name: approval-gate-debugging
description: "Use when a command is flagged as a security issue."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [approval, tirith, security-scan, smart-approval, terminal-gate, path-shadowing]
    related_skills: [root-cause-debugging, cortex-deployment-sync, file-ownership-boundaries]
---

# Approval Gate Debugging — Terminal Security-Scan False Blocks

## When to Use

- A terminal command is flagged: `Command was flagged (Security scan: security issue detected ...)`
- A **sanctioned** command (e.g. `bash ~/hermes-cortex/ops/scripts/cortex-update.sh`) still prompts for user approval
- Smart-approval escalates a routine command to the user, and the approval times out → deny
- Any command that used to run clean suddenly needs approval

**Core principle (user-corrected 2026-08-05):** an approval flag on a legitimate or
sanctioned command is a **diagnostic signal** — investigate the underlying scanner/guard
BEFORE whitelisting anything. Adding a `command_allowlist` entry to silence a flag you
don't understand masks the defect and leaves every other command still broken.

## The Two-Gate Model

Terminal commands pass TWO independent gates:

1. **Governance enforcer** (Hermes Cortex plugin) — governance-lock check. The
   sanctioned `cortex-update.sh` invocation passes this without a lock.
2. **Hermes smart approval** (`tools/approval.py`) — two sub-layers:
   - Regex `detect_dangerous_command()` — pattern matching (curl|sh, rm -rf, gateway restart, etc.)
   - **Tirith security scanner** — `tools/tirith_security.py` → external binary
     `check --json --non-interactive --shell posix -- <command>`

The enforcer sanction does **NOT** bypass gate 2. A block you see almost always comes
from gate 2.

## The Degraded-Message Tell

`"security issue detected (details unavailable)"` is the **degraded** summary. Per
`tirith_security.py` (~lines 836-840), that exact string is emitted when Tirith's JSON
output **fails to parse** — i.e. the scanner binary crashed, printed garbage, or produced
no JSON at all. It does NOT mean a real security finding. Real findings come back as
structured JSON with `findings: [...]`.

**Rule:** `details unavailable` ⇒ the scanner is broken ⇒ debug the scanner, do not
approve/allowlist the command.

## Diagnosis Recipe

```python
# 1. Regex layer passes?
from tools.approval import detect_dangerous_command
detect_dangerous_command("bash ~/hermes-cortex/ops/scripts/cortex-update.sh")
# → (False, None, None)  — regex layer is NOT the blocker

# 2. Tirith layer blocks?
from tools.tirith_security import check_command_security
check_command_security("bash ~/hermes-cortex/ops/scripts/cortex-update.sh")
# → {"action": "block", "summary": "security issue detected (details unavailable)"}

# 3. Which binary is resolved? PATH-shadowing check
import shutil; print(shutil.which("tirith"))
# If this is venv/bin/tirith → a same-named PyPI package is shadowing the real scanner

# 4. Run the resolved binary directly to see the crash
# (it ignores args, prints banner, then a traceback — e.g. socket.gaierror)
```

## PATH-Shadowing Failure Mode (root cause found 2026-08-05)

The real Tirith scanner is a compiled ELF from `sheeki03/tirith` GitHub releases,
installed at `~/.hermes/bin/tirith`. But the hermes-agent venv had a **PyPI package**
`tirith` 0.2.2 (github.com/utfsmlabs/tirith — unrelated "Monitoring software", a WAMP
client hardcoded to `ws://frameshift:8080/ws`, the original author's LAN hostname)
installed at `venv/bin/tirith`. Because `venv/bin` is FIRST on PATH, `shutil.which("tirith")`
resolved to the bogus binary. It ignores `check --json ...` args, prints
`tirith monitor 0.2.2 / connecting`, crashes on DNS resolution, exits 1 → Hermes maps
exit 1 → `block` → degraded summary.

**Consequence:** EVERY terminal command was being "scanned" by the crashing demo. The
smart-approval LLM auto-approved most silently; commands with sudo/chattr/systemctl
(like cortex-update.sh) got escalated to the user → approval timeout → deny.

### Detection

```bash
~/.hermes/hermes-agent/venv/bin/pip show tirith
# → Name: tirith, Version: 0.2.2, Summary: Monitoring software, Home-page: github.com/utfsmlabs/tirith
```

### Fix (root cause)

```bash
~/.hermes/hermes-agent/venv/bin/pip uninstall -y tirith   # nothing depends on it
# verify:
#   shutil.which("tirith") → ~/.hermes/bin/tirith
#   check_command_security(cmd) → {"action": "allow"}
```

A gateway restart clears the in-memory cached scanner path (deploy ≠ load applies to
the scanner too).

## What NOT to Do

- ❌ **Do NOT add the command to `command_allowlist`** in config.yaml to silence the flag.
  The allowlist short-circuits the entire approval gate for that command while the broken
  scanner keeps silently flagging everything else. (User: *"There is an underlying reason
  the problem exists in the first place and you are masking it."*)
- ❌ Do NOT set `approvals.mode: off` — kills all protection, not just the broken path.
- ❌ Do NOT patch `tools/tirith_security.py` or `tools/approval.py` — upstream hermes-agent
  product code, reverted on next update, and the user forbids patching the guard.
- ❌ Do NOT try to "fix" the prompt by removing gateway runtime env vars. `HERMES_EXEC_ASK`,
  `HERMES_GATEWAY_SESSION`, `HERMES_INTERACTIVE`, `_HERMES_GATEWAY` are exported by the
  RUNNING GATEWAY (`gateway/run.py`, `tui_gateway/server.py::_enable_gateway_prompts()`),
  not by config — nothing to unset, and doing so breaks approval routing. (User:
  *"DO NOT CHANGE HERMES DEFAULTS OR YOU WILL BE RESET"*, 2026-08-05.)
- ✅ DO run the resolved binary directly and read its output before deciding anything.

## Survey Before Acting (user correction 2026-08-05)

When the user reports a problem like this ("you never need my permission to update
cortex" / "why are you blocked"), the FIRST action is a survey — not a fix attempt.
This session's sequence that got corrected:

1. Diagnosed the two-gate model, found the shadow — good.
2. **Jumped straight to an env-var "fix"** (`HERMES_EXEC_ASK=1`) without loading the
   always-skills (`survey-before-action` was still unloaded) and without surveying
   where the variable actually comes from.
3. User: *"you should survey before action actually. ALWAYS"* — then
   *"DO NOT CHANGE HERMES DEFAULTS OR YOU WILL BE RESET."*

**Rule:** any investigation that may end in a config/env/system change starts with the
full always-skill set loaded and a survey of the change surface (who sets the value,
what reads it, what breaks if it changes) BEFORE proposing or making any edit. When the
user pushes back on a fix, the correction is a signal to survey deeper, not to act faster.

## Verification Checklist

- [ ] `detect_dangerous_command(cmd)` returns `(False, None, None)` (regex layer clean)
- [ ] `shutil.which("tirith")` resolves to the real binary, not `venv/bin/tirith`
- [ ] `check_command_security(cmd)` returns `action: allow`
- [ ] The original command runs with no security flag and no approval prompt
- [ ] No `command_allowlist` entries were added to work around the scanner

## References

- `references/tirith-shadow-2026-08-05.md` — full evidence chain: degraded-message code
  path, binary crash traceback, package metadata, PATH resolution order, fix + verification
