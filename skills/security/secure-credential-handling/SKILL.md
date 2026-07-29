---
name: secure-credential-handling
description: Handle passwords, API keys, tokens, and secrets securely when using terminal/read_file/execute_code tools — avoid exposing sensitive values in tool call parameters or chat output.
version: 1.0.0
author: Hermes Cortex
trigger: before reading or passing any credential file, password, API token, or secret
---

# Secure Credential Handling

**Core principle:** tool call parameters (especially `terminal` commands and `read_file` paths) are VISIBLE in full in the chat. Every session sees every command string. Treat terminal command strings as a public log.

## Hard Rules

### 1. Never write the secret value into a command string

```bash
# ❌ WRONG — password appears as literal text in the tool call
printf 's3cur3-p@ss' > /tmp/passwd_clean.txt
curl -u "admin:s3cur3-p@ss" https://...

echo 'ghp_xxxxxxxxxxxx' | gh auth login --with-token

# ✅ RIGHT — password never appears in tool call text
# Use cat from file in $() — expands AFTER tool call is sent
curl -sk --basic -u "root:$(cat ~/.asus)" https://...

# Read tokens from file via stdin redirect
gh auth login --with-token < ~/.github_token_path
```

### 2. Never use read_file on credential files

```bash
# ❌ WRONG — read_file displays the file contents in chat output
read_file(path="~/.asus")

# ✅ RIGHT — check file with safe alternatives
wc -l ~/.asus              # just count lines
stat ~/.asus                # file metadata only
echo "password saved"       # you know it exists, no need to display
```

### 3. For repeated use, stage to a temp file silently

```python
# Copy credential to temp file ONCE (terminal shows cp command, not content)
terminal("cp ~/.asus /tmp/passwd_clean.txt")

# Then reference via $() subshell on every subsequent command
terminal("curl -sk -u \"root:$(cat /tmp/passwd_clean.txt)\" https://...")
```

**Why this works:** `$(cat /tmp/passwd_clean.txt)` in a terminal tool call shows the file path but NOT the file content. The shell expands it after the command is displayed.

## Defense Layers

Three layers protect against credential leaks in `terminal()` commands:

1. **Behavioral** — this skill + SOUL.md principle on every agent
2. **Pre-commit scan** — `secret-leak-detector.sh` runs in `pre-commit-score` hook, scans staged files for printf/echo + credential patterns
3. **Runtime watchdog** — `secret-leak-watchdog` (no_agent cron, every 4h) scans cron outputs and session files for leaked patterns, alerts via inbox

Set `SKIP_SECRET_SCAN=1` to bypass the pre-commit detector (emergencies only).

## Pitfalls

### printf with literal secret
```bash
# EXPOSES the password — printf shows the value in the command string
printf 'myP@ssw0rd!' > /tmp/pass.txt
```
**Fix:** `cp ~/secret_file /tmp/pass.txt` — no content leakage.

### Shell `&` in password causes silent truncation
If the password contains `&` and you use inline `$(cat ~/file)`, the shell expansion is fine within `$()`. But if you accidentally paste the password directly into the command, the `&` background-processes the rest. Always use a file reference, never inline.

### Terminal output vs command display
The `terminal` tool shows the `command` parameter in full. Even though this is tool metadata (not standard output), it IS visible to the user and recorded in the session log. Treat it as a broadcast channel.

### Base64 encoding for Basic Auth
When you need HTTP Basic Auth: let curl handle it with `-u "user:$(cat /tmp/pass)"`. The base64 encoding happens on the server side of curl, never in your visible command string.
