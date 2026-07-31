---
name: shell-scripting
description: Shell scripting patterns, portability pitfalls, and cross-platform compatibility for bash/awk scripts in the Hermes Cortex ecosystem.
version: 1.1.0
author: Hermes Cortex
platforms: [linux, macos]
---

# Shell Scripting Patterns

Patterns, pitfalls, and portability guidance for shell scripts in the Hermes Cortex ecosystem. Covers bash and awk — the two most common scripting languages in the repo.

## Bash Pitfalls

### `set -e` + `((var++))` = silent exit

A **classic `set -e` trap**. When a variable starts at 0, `((var++))` evaluates to 0 (the post-increment result), which is falsy in shell arithmetic context. With `set -e`, this causes an immediate script exit:

```bash
# ❌ KILLS THE SCRIPT when var=0
set -euo pipefail
var=0
# ...some loop...
((var++))    # exit code 1 (falsy value 0) → `set -e` kills the script
echo "This never runs"
```

```bash
# ✅ Safe alternative
var=$((var + 1))
```

```bash
# ✅ Also safe: pre-increment with : prefix to suppress failure
((++var))    # evaluates to 1 (truthy), exit code 0
```

**Best practice:** Always use `var=$((var + 1))` when `set -e` is active and the variable could be 0. Or use `: $((var++))` to suppress the exit code:

```bash
: $((var++))
```

### `set -e` + failed command substitution in an assignment = silent exit

A **silent-kill trap** distinct from `((var++))`: `VAR=$(cmd || fallback)` — when BOTH the command and its fallback fail, the assignment's exit status is the command substitution's non-zero status, and `set -e` aborts the script with **exit 1 and NO output** (stderr is typically already `2>/dev/null`'d):

```bash
# ❌ KILLS THE SCRIPT silently when both branches fail
set -euo pipefail
ORCH_CONFIG=$(git show HEAD:docs/config.txt 2>/dev/null || cat docs/config.txt 2>/dev/null)
#   → file missing at HEAD AND on disk → both fail → assignment returns 1
#     → set -e exits before the next line, no message printed

# ✅ Safe — || true makes the LAST command of the AND-OR list always succeed
ORCH_CONFIG=$(git show HEAD:docs/config.txt 2>/dev/null || cat docs/config.txt 2>/dev/null || true)
if [[ -n "$ORCH_CONFIG" ]]; then ... fi   # empty = "no config", gate on -n
```

**The rule:** any optional/config file read with fallbacks must terminate the chain with `|| true`, and downstream logic must gate on `[[ -n $VAR ]]`. A missing optional file should mean "feature off", never "script dies".

**Real bug (2026-07-31):** `pre-commit-score`'s orchestrator-only-paths guard read `docs/orchestrator-only-paths.txt` this way. Repos without the file (e.g. client project repos) had EVERY non-orch commit fail with exit 1 and zero output. One `|| true` fixed it fleet-wide.

### `set -u` + uninitialized counter variable = premature exit

When a script uses `set -u` (or `set -euo pipefail`) and a variable like `REMOVED` is only conditionally incremented (e.g., inside a loop that may iterate zero times), referencing it without a default value causes an immediate exit:

```bash
# ❌ FAILS when REMOVED was never set — 'REMOVED: unbound variable' → script exits 1
[[ "$REMOVED" -gt 0 ]] && warn "${REMOVED} deprecated file(s) removed"

# ✅ SAFE — provides fallback for unset var
[[ "${REMOVED:-0}" -gt 0 ]] && warn "${REMOVED} deprecated file(s) removed"
```

This pattern appears in summary sections where a counter is only incremented conditionally. The fix is the `:-` default-value syntax: `${VAR:-0}`.

**Detection:** Any reference to a counter variable outside the loop/section that increments it may be unset if no items matched. Common culprits: `REMOVED`, `DELETED`, `ERRORS`, `MODIFIED`. Run with `bash -u` to catch these before shipping.

**Real bug:** `cortex-update.sh` line 1334 had `[[ "$REMOVED" -gt 0 ]]` — when `--force-all` found nothing to remove, `REMOVED` was never initialized, and the script exited with code 1 despite a successful deployment. The fix was `${REMOVED:-0}`.

### `trap` with `set -e` — unexpected exits

When using `trap ... EXIT` with `set -euo pipefail`, a function called inside the trap exit handler that fails can cause cascading exits during already-running cleanup. Prefer `trap ... ERR` over relying on return codes.

### Quoting — always double-quote variable expansions

```bash
# ❌ Word splitting on spaces/glob chars
echo $filename   # "my file.txt" becomes two args: "my" and "file.txt"

# ✅ Safe
echo "$filename"
```

### `\$` vs `$` in double-quoted strings — escaped dollar does NOT expand

A subtle bash footgun: `\$` inside double quotes escapes the `$`, producing a literal `$` character instead of expanding the variable:

```bash
# ❌ WRONG — passes the literal string "$HOME"
workdir="\$HOME"
echo "$workdir"       # prints: $HOME (literal)
mkdir -p "$workdir"   # creates directory named "$HOME"
```

```bash
# ✅ CORRECT — expands $HOME to actual path
workdir="$HOME"
echo "$workdir"       # prints: /home/moses
```

**How this bites you:**

- `install-crons.sh` had `"\$HOME"` — bash passed literal `$HOME` to `hermes cron create --workdir`
- The CLI requires an absolute path starting with `/`
- The literal string `$HOME` doesn't start with `/` → job silently not created
- The script printed "Created cron" because `hermes` returned exit 0 (it parsed the arguments but rejected the invalid workdir)

**The pattern is deceptive because `\$` IS a valid escape in double quotes — it just doesn't do what you want.** The backslash escapes the `$` from being a variable expansion marker, turning it into a literal dollar sign.

| Escape sequence | In double quotes | Produces |
|----------------|-----------------|----------|
| `\$HOME` | Escapes `$` → literal `$`, then `HOME` | `$HOME` (literal string) |
| `$HOME` | Variable expansion | `/home/moses` |
| `\\$HOME` | Literal `\`, then `$HOME` expanded | `\/home/moses` |
| `\$HOME` in single quotes | All literal | `\$HOME` |

**How to detect:** When debugging, always verify what a string actually contains:

```bash
# Check what bash passes
workdir="\$HOME"
echo "workdir value: $workdir"                # prints: $HOME
echo "workdir is absolute: $( [[ "$workdir" == /* ]] && echo YES || echo NO)"  # prints: NO
xxd <<< "$workdir"                            # see the literal byte values
```

**Best practice for paths in scripts that will run on multiple machines:** Always `"$HOME"` (un-escaped) when you intend the user's home directory. Use a full absolute path like `"/home/moses"` only when the path must be hardcoded (and document why). Use `"${HOME}/subdir"` when you need a subdirectory. Never `"\$HOME"` — it never does what you want in this context.

## Testing a Script Block in Isolation (Hook Guards, Conditionals)

When you change a conditional guard inside a larger bash script (git hooks,
installer guards), you often **can't trigger the changed branch from your own
environment** — e.g. orchestrators skip the non-orch guard in
`pre-commit-score` by design, and an in-flight sibling change may not be
deployed yet. Extract the block and run it with stubs instead of staging a
real commit:

1. **Extract the real block, anchored on stable markers** (never line
   numbers — they shift the moment you edit):
   ```bash
   awk '/^REPO_ROOT=/{p=1} p{print} /Reflexion gate/{exit}' \
     ops/scripts/pre-commit-score > /tmp/guard-block.sh
   ```
2. **Prepend a stub preamble** forcing the branch you can't reach:
   ```bash
   set -euo pipefail
   _detect_orch() { return 1; }          # force the non-orch branch
   _log_impersonation() { echo >/dev/null; }
   ```
3. **Run from the real repo** so `git show HEAD:` / `git rev-parse` resolve.
   Case matrix (bug → fix → enforcement preserved):
   - *bug*: point the config path at a nonexistent file → expect the failure
     (silent exit 1)
   - *fixed*: apply the one-line fix → expect pass-through
   - *guard*: stub STAGED_FILES with a restricted path → expect block + exit 1
4. **Re-run against the DEPLOYED copy after deploy** — verify the runtime
   path, not just the source (`diff deployed repo` first; line numbers
   differ between source and deployed).
5. **sed delimiter pitfall:** when the pattern contains `||`, `s|old|new|`
   dies with "unknown option to `s'`" — use `@`: `s@old@new@`.

Worked example (2026-07-31): `pre-commit-score` ORCH_CONFIG silent failure —
`set -euo pipefail` + `VAR=$(git show HEAD:... || cat ... 2>/dev/null)` died
silently (exit 1, no output) in repos without `docs/orchestrator-only-paths.txt`.
Reproduced via this harness, fixed with `|| true`, all three cases verified,
deployed, doctor clean.

## Awk Portability

### Beware: mawk vs gawk syntax

Most Linux distributions (including Ubuntu) ship **mawk** as the default `awk`, not **gawk**. While both implement POSIX awk, they differ in what GNU extensions they support.

**The number one mawk trap:** bare `if` at the top level of an awk program.

```awk
# ❌ VALID in gawk, SYNTAX ERROR in mawk
awk 'if (match($0, /pattern/)) { action } END { ... }'
```

mawk requires the body to be inside `{ }`:

```awk
# ✅ Works in BOTH mawk and gawk
awk '{ if (match($0, /pattern/)) { action } } END { ... }'
```

The error message is diagnostic:
```
awk: line 2: syntax error at or near if
```

**Why this matters:** The repo's `nginx-security-scanner.sh` had this exact bug — bare `if` inside a `timeout 10 awk -v ...` pipeline. It only manifested on Ubuntu/mawk systems, while macOS (which ships gawk) ran fine. The fix was wrapping the body in `{ }`.

### Always check which awk is default

```bash
# On Linux (Ubuntu/Debian):
which awk        # → /usr/bin/awk (mawk symlink)
awk --version    # → mawk 1.3.4 ...

# On macOS:
which awk        # → /usr/bin/awk (gawk or macOS awk)
```

### Key differences table

| Feature | mawk | gawk | Portability advice |
|---------|------|------|--------------------|
| Bare `if` at top level | ❌ Syntax error | ✅ Works | Wrap in `{ }` |
| `match()` with 3rd arg array | ❌ | ✅ | Use `substr()` + `RSTART`/`RLENGTH` |
| `gensub()` | ❌ | ✅ | Use `gsub()` or `sub()` |
| `strftime()` | ❌ | ✅ | Use external `date` command |
| `PROCINFO` | ❌ | ✅ | Avoid |
| Performance | Faster (~2x) | Slower for large files | Use mawk for parsing, gawk for scripting |

### Safe awk patterns

```awk
# ✅ Use RSTART/RLENGTH for extracting matches (works in both)
{
  if (match($0, /\[[^]]+\]/)) {
    ts = substr($0, RSTART+1, RLENGTH-2)
  }
}

# ✅ Use for-loop array iteration (works in both, though order differs)
END {
  for (k in arr) print k, arr[k]
}

# ❌ Don't use asort / asorti / PROCINFO (gawk-only)
```

## Resolving the Repo Root from a Nested Script — Count the Depth

`CORTEX_REPO="$(cd "$(dirname "$0")/../.." && pwd)"` only works when the
script sits exactly 2 levels below the repo root. A script in
`ops/install/deploy/nginx/` is 4 levels deep — `../..` resolves to
`.../ops/install`, and every path built on it doubles a segment:

```
Source not found: .../ops/install/ops/install/deploy/nginx/fix-blocked-ips.py
                              ^^^^^^^^^^^^^ duplicated segment
```

**Confirmed 2026-07-31:** this bug existed in THREE sibling deploy scripts
(`deploy-fix-blocked-ips.sh`, `deploy-sudoers.sh`, `deploy-blocked-ips.sh`)
and surfaced as a user-visible failure only in one. When you find one
path-walk-up bug, grep the whole tree for the same pattern:
`grep -rn 'dirname "$0"/\.\.' ops/`.

**Robust pattern** — prefer git, fall back to counted walk-up:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORTEX_REPO="$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$CORTEX_REPO" ] || [ ! -d "$CORTEX_REPO" ]; then
  CORTEX_REPO="$(cd "$SCRIPT_DIR/../../../.." && pwd 2>/dev/null || echo "$HOME/hermes-cortex")"
fi
```

**Verify by running from the script's real location**, not an inline test:
inline `$(dirname "$0")` inside a `bash -c` string gives `$0` = the shell,
so the test silently tests the wrong path. Compute from the actual script
path (`SCRIPT=/abs/path/script.sh; dirname "$SCRIPT"`) or run the script
itself.

## `: "${VAR:-$HOME}"` Validates but Does NOT Assign

A bare `:` with parameter expansion is a validate-only idiom — it expands
the fallback and discards it. `VAR` stays EMPTY, and every downstream path
built on it resolves to a root-level path (or a literal). If you need the
fallback applied, ASSIGN:

```bash
# ❌ REAL_HOME stays empty if getent fails — TARGETS become /.hermes/...
: "${REAL_HOME:-$HOME}"
# ✅ assigns the fallback
REAL_HOME="${REAL_HOME:-$HOME}"
```

**Detection:** any `: "${VAR:-...}"` line followed by uses of `$VAR` is a
latent bug. The idiom only makes sense when the point is to *fail loudly*
under `set -u` — if you want the default, assign it.

## Idempotent Installer Patterns: Dual Detection

When an installer script (e.g., `install-crons.sh`) must avoid creating duplicate
artifacts, the detection method matters:

### Single-source detection (brittle)

```bash
# ❌ Only checks jobs.json — fails if file is locked, empty, or the store
#    format has a transitional state (atomic_replace write, missing file, etc.)
cron_exists() {
  if [[ -f "$CRON_JOBS_FILE" ]]; then
    ... parse JSON, look for name ...
    if found; then return 0; fi
  fi
  return 1  # false negative → duplicate created
}
```

### Dual detection (robust)

```bash
cron_exists() {
  local name="$1"

  # Method 1: Fast path — parse the store file directly
  if [[ -f "$CRON_JOBS_FILE" ]]; then
    if python3 -c "... check name in JSON ..." 2>/dev/null; then
      return 0
    fi
  fi

  # Method 2: Fallback — query the running system via CLI
  if command -v "${CLI_CMD}" &>/dev/null; then
    if "${CLI_CMD}" list --all 2>/dev/null | grep -q "Name:[[:space:]]*${name}$"; then
      return 0
    fi
  fi

  return 1
}
```

**Why this works:** Method 1 is fast (direct file read, 1ms) and covers the common
case. Method 2 queries the live system's authoritative API—it works even when
the store file is being atomically replaced, has a lock held, or is in an
inconsistent state. The CLI is always the authoritative source of what jobs
actually exist.

**Tradeoff:** The CLI is slower (300-500ms) and requires external command
availability. Method 1 handles 99% of calls; Method 2 only fires when the file
check fails — which is exactly when you need it (transitional states).

### When to apply this pattern

This pattern applies to any installer that creates artifacts in a system-managed
store:
- Cron jobs (`hermes cron create` — store is `jobs.json`)
- Plugins (`hermes plugins install` — store is plugin registry)
- Skills (`hermes skills install` — store is skill registry)
- Config entries, secrets, user settings

The key insight: **the store file is an implementation detail.** The CLI is the
stable API. Checking the file first is an optimization — falling back to the
CLI is correctness.

### Coupled installations — independent artifact detection

When a function installs two independent artifacts (e.g., pre-commit AND
pre-push hooks), EACH artifact must have its own skip-if-current logic.
An early return for "A is already current" that skips B's installation
is a bug:

```bash
# ❌ BAD: install_push_hook only called on NEW installs of pre-commit
install_hook() {
  if already_current; then
    SKIPPED=$((SKIPPED + 1))
    return                     # ← silently skips push hook!
  fi
  cp "$SOURCE" "$DEST"
  install_push_hook "$repo"    # ← only reached on new installs
}

# ✅ GOOD: each function owns one artifact, caller orchestrates both
install_hook() {
  if already_current; then
    SKIPPED=$((SKIPPED + 1))
    return
  fi
  cp "$SOURCE" "$DEST"
}
install_push_hook() {
  if already_current; then
    return
  fi
  cp "$SOURCE" "$DEST"
}
# Caller always calls both independently:
install_hook "$repo"
install_push_hook "$repo"
```

**Symptom:** outputs "Already current" or "Updated hook" for artifact A, but
artifact B is never written. Silent — no error, no warning.

**Detection in review:** Look for any function that (a) calls another install
function, (b) has an early return path, and (c) the called function is NOT
invoked before that return.

## Batch Pipeline Pattern: Replace Per-Item Loops with Pipelines

When processing a list of items where each item needs validation, filtering, or deduplication, the natural instinct is a `while read` loop. But each external command (grep, sed, awk) inside the loop spawns a **subprocess per iteration** — leading to thousands of process spawns for large files.

### ❌ Per-Item Loop (Slow — O(n) process spawns)

```bash
# Each of 2257 source lines spawns 4 grep subprocesses = ~9000 spawns
while IFS= read -r ip; do
  [ -z "$ip" ] && continue
  [[ "$ip" == \#* ]] && continue
  if ! echo "$ip" | grep -qE '^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$'; then
    INVALID=$((INVALID + 1)); continue
  fi
  if echo "$ip" | grep -qE '^127\.'; then
    INVALID=$((INVALID + 1)); continue
  fi
  if grep -q "^deny ${ip};" "$BLOCK_FILE" 2>/dev/null; then
    SKIPPED=$((SKIPPED + 1))
  else
    echo "deny ${ip};" >> "$BLOCK_FILE"
    ADDED=$((ADDED + 1))
  fi
done < "$SOURCE_FILE"
```

**Cost for a 2000-line file:** ~8000 process spawns + O(n^2) file scanning for dedup ≈ 2 minutes runtime.

### ✅ Batch Pipeline (Fast — O(1) process spawns)

```bash
# Replace the entire loop with a single pipeline — 5 grep calls total
cat "$SOURCE_FILE" | \
  grep -vE '^\s*(#|$)' | \                    # strip comments/blanks
  grep -E '^[0-9]{1,3}\.[0-9]{1,3}\.' | \     # valid IPv4
  grep -vE '^(127\.|10\.|0\.|172\.' | \        # reject private ranges
  grep -vxF -f <(sed -n 's/^deny //;s/;$//p' "$EXISTING_FILE") \  # batch dedup
  > "$NEW_IPS"

# Append results in one write
sed 's/^/deny /; s/$/;/' "$NEW_IPS" >> "$BLOCK_FILE"
```

**Cost for a 2000-line file:** 5 process spawns total + O(n) file scan for dedup ≈ < 1 second.

### When to Apply

| Signal | Replacement |
|--------|-------------|
| `while IFS= read -r X; do echo "$X" \| grep` | Single `grep` pipeline with `|` |
| Per-item check against a set of known values | `grep -vxF -f <(process_substitution)` |
| Per-item file append | Batch `>>` at end |
| Per-item arithmetic counter | `wc -l` on filtered intermediate file |
| `[ -z "$X" ] && continue` at top of loop | `grep -vE '^\s*(#|$)'` as first pipeline stage |

### Key Techniques

| Technique | One-liner | Use case |
|-----------|-----------|----------|
| **Batch dedup** | `grep -vxF -f <(existing_patterns)` new_ips | Remove lines already present in another file — O(n+m), single file scan |
| **Process substitution** | `<(...)` | Feed a dynamically-generated filter without a temp file |
| **sed transform** | `sed 's/^/prefix/; s/$/suffix/'` | Wrap each line with formatting in one pass |
| **Pipeline rejection** | `cat \| grep -v \| grep -E \| grep -v` | Chain filter stages — each stage narrows the set |
| **Count via wc** | `COUNT=$(wc -l < "$FILE")` | Get line count from a filtered intermediate file |

### Why This Matters

| Metric | Per-Item Loop | Batch Pipeline | Improvement |
|--------|--------------|----------------|-------------|
| Process spawns for 2000 items | ~8000 | ~5 | **1600x** |
| File scans for dedup | ~2000 (O(n^2)) | ~1 (O(n)) | **2000x** |
| Wall time | ~2 min | < 1 sec | **~120x** |

### Portability: `grep -E` over `grep -P`

The batch pipeline approach naturally uses `grep -E` (extended regex) instead of `grep -P` (Perl regex), because piped greps compound the cost of `-P` (which loads the PCRE library). This is a **portability bonus**: `grep -P` is not available on macOS (native grep doesn't support it), while `grep -E` works everywhere.

| Flag | Linux | macOS | Performance |
|------|-------|-------|-------------|
| `grep -P` | ✅ | ❌ (`-P` not supported) | Slower (PCRE library load) |
| `grep -E` | ✅ | ✅ | Faster (ERE engine) |
| `grep -F` | ✅ | ✅ | Fastest (fixed string, no regex) |

**Conversion guide:**
- `\d` → `[0-9]` (the most common `-P` escape; always portable)
- `\s` → `[[:space:]]` (POSIX character class, works everywhere)
- `\b` → use `(^|[^[:alnum:]])...([^[:alnum:]]|$)` manually (awkward but portable)
- `(?!...)` lookahead → not portable; restructure logic

When you need a regex that works on both platforms, **write it in `-E` first** and only reach for `-P` when the pattern genuinely requires lookahead/backreference (very rare in shell scripts — use Python for that).

## Cross-Platform Paths

### Finding executables

```bash
# Use command -v, not which
command -v nginx  # POSIX-compliant, works everywhere

# For platform-aware binary paths:
for path in /usr/sbin/nginx /usr/local/bin/nginx /opt/homebrew/bin/nginx; do
  [ -x "$path" ] && NGINX_BIN="$path" && break
done
```

### `timeout` command

```bash
# Linux uses `timeout`, macOS uses `gtimeout` (brew coreutils)
TIMEOUT_CMD=""
for cmd in timeout gtimeout; do
  if command -v "$cmd" &>/dev/null; then
    TIMEOUT_CMD="$cmd"
    break
  fi
done
```

### Coupled installations — one function installing multiple independent artifacts

When a function installs two independent artifacts (e.g., pre-commit hook AND pre-push hook), BOTH must be installed regardless of whether artifact A was newly installed or already current. An early return for "A already current" that silently skips B's installation is a bug.

```bash
# ❌ BAD: install_push_hook only called on NEW installs
install_hook() {
  if already_current; then
    SKIPPED=$((SKIPPED + 1))
    return                     # ← silently skips push hook!
  fi
  cp "$SOURCE" "$DEST"
  install_push_hook "$repo"    # ← only reached on new installs
}

# ✅ GOOD: each function owns one artifact, caller orchestrates both
install_hook() {
  if already_current; then
    SKIPPED=$((SKIPPED + 1))
    return
  fi
  cp "$SOURCE" "$DEST"
}
install_push_hook() {
  if already_current; then
    return
  fi
  cp "$SOURCE" "$DEST"
}
# Caller always calls both independently:
install_hook "$repo"
install_push_hook "$repo"
```

**The symptom:** Script outputs "Installed hook: ..." or "Already current" for pre-commit, but pre-push is never written. Silent — no error, no warning.

**How to detect in review:** Look for any function that (a) calls another install function, (b) has an early return path, and (c) the called function is NOT invoked before that return. If `install_thing_A` calls `install_thing_B`, but `return` on line N can skip the call on line N+M, it's a latent bug.

**Fix pattern:** Make each install function self-contained with its own skip-if-current logic. The caller (or a dispatch loop) calls each function independently. `install_push_hook` handles its own "already current" check — the caller never decides whether to call it.

### `sudo -n true` — always check for passwordless sudo before using sudo in scripts

When a script needs `sudo` for system-level operations (config file writes, service reloads), check that sudo works without a password FIRST. `command -v sudo` only checks that the binary exists, not that it's usable non-interactively.

```bash
# ❌ WRONG — sudo exists but may require a password
if command -v sudo &>/dev/null && [[ "$dest" == /etc/* ]]; then
  sudo cp "$tmp" "$dest"   # fails with "sudo: a password is required"
fi

# ✅ CORRECT — verify passwordless sudo before attempting
if [[ "$dest" == /etc/* ]]; then
  if command -v sudo &>/dev/null && sudo -n true 2>/dev/null; then
    sudo mkdir -p "$(dirname "$dest")"
    sudo cp "$tmp" "$dest"
    sudo chmod 644 "$dest"
    info "Deployed: $dest"
  else
    warn "Passwordless sudo not available — skipping $dest"
    warn "Config written to: $tmp (not deployed)"
  fi
else
  cp "$tmp" "$dest"        # no sudo needed for user-writable paths
fi
```

**Why `|| true` on `mkdir` is a trap:** `sudo mkdir -p` with `|| true` silently swallows the failure when sudo needs a password. The next command (`sudo cp`) then hard-fails. Always check `sudo -n true` upfront.

**Providing the fix:** When skipping due to missing passwordless sudo, print the exact sudoers rule the user can run:

```bash
echo "${USER} ALL=(ALL) NOPASSWD: /usr/sbin/nginx, /bin/mkdir, /bin/cp, /bin/chmod, /bin/ln" \
  | sudo tee /etc/sudoers.d/hermes-cortex
```

This lets the user fix it in one copy-paste next time.

A subtle bug: `command -v "$candidate"` succeeds as a test (exit 0) even though `$candidate` is a bare name. If you then assign `$candidate` instead of capturing `command -v`'s stdout, you get the bare name — and `python3 "$SCORE_CYCLE"` tries to open `./score-cycle` (doesn't exist):

```bash
# ❌ WRONG — tests with the resolved path but assigns the bare name
for candidate in score-cycle ~/.local/bin/score-cycle; do
  if command -v "$candidate" &>/dev/null 2>&1; then
    SCORE_CYCLE="$candidate"   # ← bare name, not resolved path
    break
  fi
done
python3 "$SCORE_CYCLE" ...     # tries ./score-cycle → fails silently

# ✅ CORRECT — capture command -v stdout to get the resolved path
for candidate in score-cycle ~/.local/bin/score-cycle; do
  if resolved=$(command -v "$candidate" 2>/dev/null); then
    SCORE_CYCLE="$resolved"    # ← /home/user/.local/bin/score-cycle
    break
  fi
done
python3 "$SCORE_CYCLE" ...     # works
```

**Root cause:** `command -v` serves two roles — it's both a test (returns 0 if found) AND a value (prints the resolved path). Using `command -v "$candidate" &>/dev/null` discards the value output, then `$candidate` gives you back the iteration variable. The fix uses command substitution `resolved=$(...)` to capture the output.

**The 2>/dev/null camouflage:** This bug is easy to miss because the `|| echo` fallback swallows the error. `python3 score-cycle` fails → `|| echo '{"decision":"LOOP"}'` fires → everything looks fine. Only checking the DB reveals nothing was written. Always run without `2>/dev/null` when debugging.

### `date` format differences

```bash
# Linux:
date -d "-60 minutes" "+%d/%b/%Y:%H:%M:%S"

# macOS:
date -v-60M "+%d/%b/%Y:%H:%M:%S"

# Portable pattern:
cutoff="$(date -v-${MINS}M +format 2>/dev/null || date -d "-${MINS} min" "+format")"
```

## Systematic Installer Script Auditing

Before shipping changes to installer scripts (`install-crons.sh`, `setup.sh`, etc.), run this checklist to catch the class of bugs that `--force` and dry-run mode don't surface.

### Audit checklist

1. **Coverage completeness** — Does the script have any reverse operation (uninstall, cleanup, reset) that lists specific items? Verify the list matches the current set of items the script creates. Missing items mean the reverse operation silently leaves artifacts.

2. **Variable naming overlap** — Are any variables used for two different purposes depending on mode? Common pattern: `CREATED` used for both dry-run "would create" count and real "did create" count. Use separate names (`WOULD_CREATE` vs `CREATED`) or the summary section becomes misleading.

3. **Dead success checks** — Look for any `if [[ $? -eq 0 ]] && grep -q PATTERN /dev/stdin`. This is a classic bug: the command's output already went to the terminal (not stdin), so the grep reads from an empty stdin and always fails. The success message never fires. Fix: capture output in a variable and check it:
   ```bash
   # ❌ DEAD — grep reads empty stdin
   result=$(some_cmd) 2>&1
   if [[ $? -eq 0 ]] && grep -q SUCCESS /dev/stdin 2>/dev/null; then
       echo "Success"  # Never executes
   fi

   # ✅ CORRECT — check captured output
   result=$(some_cmd 2>&1)
   if [[ "$result" == *"SUCCESS"* ]]; then
       echo "Success"
   fi
   ```

4. **Formatting consistency for positional-arg functions** — Functions that take 8+ positional arguments (like `create_cron`) are hard to audit when calls mix compact and multi-line styles:
   ```bash
   # Hard to review — must count empties
   create_cron "my-cron" "0 5 * * *" "script.py" "" "" "" "origin" "" "true"

   # Easy to review — each field on its own line
   create_cron "my-cron" "0 5 * * *" \
     "script.py" \
     "" \
     "" \
     "" \
     "origin" \
     "" \
     "true"
   ```
   Standardize ALL calls to multi-line. The grep to find compact patterns: `grep -n '"" "[^"]*" "" "' ops/scripts/install-crons.sh` (matches consecutive quoted empties).

5. **Path validation for file-based lookups** — When the script reads or writes a file at a hardcoded path (`CRON_JOBS_FILE`, `STATE_FILE`), verify against the actual runtime path. Common mismatch: `$HERMES_HOME` defaulting to `~/.hermes-cortex/` when the runtime expects `~/.hermes/`. Test by running outside the normal execution context.

6. **Script exists check coverage** — The `script_exists` helper typically checks `~/.hermes-cortex/scripts/` and the repo source. If the script could also be a CLI wrapper symlink in `~/.local/bin/`, add that path. Missing paths produce "Script not found" warnings silently — no delivery, no alert, just a scroll-past in the output.

### Real findings from this checklist applied to `install-crons.sh` (870 lines)

| Check | Finding |
|-------|---------|
| Coverage completeness | Uninstall list missed 9 of 34 crons |
| Variable naming overlap | `CREATED` used for both dry-run and real mode |
| Dead success checks | `setup_ollama_provider` grep'd `/dev/stdin` — ALWAYS empty |
| Formatting consistency | 14 compact calls mixed with multi-line calls |
| Path validation | `CRON_JOBS_FILE` path was correct (verified) |
| Script exists coverage | Missing `~/.local/bin/` for CLI wrapper symlinks |

## Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|------|
| `declare -A` (associative arrays) on macOS | `declare: -A: invalid option` on macOS (ships bash 3.2, needs 4+) | Use parallel indexed arrays: `ARR_KEYS=() ARR_VALS=()` + numeric-index loop. Or use a Python script for complex maps. |
|---------|---------|------|
| `set -e` + `((var++))` | Script exits silently mid-function when counter is 0 | Use `var=$((var + 1))` or `: $((var++))` |
| `\\$` in double-quoted strings | Literal string `$HOME` passed instead of expanded path | Remove `\\` before `$`: `"$HOME"` not `"\\$HOME"` |
| Bare `if` in mawk | `awk: line 2: syntax error at or near if` on Ubuntu | Wrap awk body in `{ }` |
| Missing `timeout` on macOS | `command not found: timeout` | Fall back to `gtimeout`, then no timeout |
| `grep -P` on macOS | `grep: invalid option -- P` | macOS grep doesn't support Perl regex; use `grep -E` or install `ggrep` |
| **Per-item loop with grep inside** | Script takes minutes for 2000 items | Replace with batch pipeline — 5 grep calls total |
| **grep ADDED from /dev/stdin** | Success message for an operation never fires, but no error either | Capture output in a variable and check it: `[[ "$_var" == *"ADDED"* ]]` |
| **Counter var overlap (dry-run vs real)** | Summary shows misleading counts | Use separate vars: `WOULD_CREATE` vs `CREATED` |
| **Mixed formatting for positional-arg functions** | Hard to audit — must count empties to understand args | Standardize all calls to multi-line, one field per line |
| **Missing script existence path** | "Script not found" warning scrolls past silently | Check all possible locations: `scripts/`, repo source, `~/.local/bin/` |
