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

### `| head -N` under `set -euo pipefail` = silent SIGPIPE abort

**A silent-kill trap that only fires on LARGE outputs:** truncating a pipeline with `head -N` makes `head` exit after N lines; the producer then gets SIGPIPE (exit 141). With `pipefail`, the pipeline status becomes 141, and with `set -e` the whole script aborts — **silently, mid-deploy, exit 141** (or exit 0 if the caller pipes the script's output without checking `PIPESTATUS`).

```bash
# ❌ ABORTS the script when $src has >20 lines not in $dest
set -euo pipefail
local_only_lines=$(comm -23 <(sort "$dest") <(sort "$src") 2>/dev/null | head -20)
#   → head reads 20 lines, closes the pipe → comm gets SIGPIPE (141)
#     → pipefail propagates 141 → set -e exits BEFORE the copy_file below

# ✅ Safe — sed consumes ALL input; no SIGPIPE possible
local_only_lines=$(comm -23 <(sort "$dest") <(sort "$src") 2>/dev/null | sed -n '1,20p')
```

**The rule:** under `set -euo pipefail`, never truncate a pipeline with `head`/`tail` unless you add `|| true` (which masks the real status). Prefer `sed -n '1,Np'` — it reads everything, so the producer never gets SIGPIPE. This applies in `$(...)` assignments too: the substitution's exit status is the pipeline's under pipefail.

**Real bug (2026-08-04):** `cortex-update.sh`'s AGENTS.md sync used `comm | head -20`. Any deploy where the local `~/.hermes/AGENTS.md` diverged from the repo by >20 lines (e.g. an AGENTS.md trim) silently skipped EVERYTHING after the sync — mycortex migrations, nginx/plugin deploys, soul-merge, the update-commit save, and the lock purge — while `update-commit` stayed stale and the doctor reported "Deploy sync FAIL". The exit was masked entirely when the script was invoked through a pipe (`bash script.sh | tail` returns tail's 0). Same latent pattern fixed in the two `stale-ref-watchdog` scripts (`find | head -20`).

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

**Real bug:** `cortex-update.sh` line 1334 had `[[ "$REMOVED" -gt 0 ]]` — when `cortex-update.sh` found nothing to remove, `REMOVED` was never initialized, and the script exited with code 1 despite a successful deployment. The fix was `${REMOVED:-0}`.

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

## Deploy-Time Mode Overrides — Run AFTER the Unlock, Not at Register Time

When a deploy script (e.g. `cortex-update.sh`) locks enforcement files immutable
(chattr +i / uchg) at the end of its run, any `chmod` at **register time** (the
top-level register block, before the per-file loop unlocks) fails silently on
the still-immutable file. And a content-only change detector (`needs_update()`
comparing checksums) never re-copies an identical-content file — so a stale
mode (e.g. a July-era 444 on a hook) sticks forever. Real case 2026-08-03:
`chmod 700 hooks/post-merge` at register time ran before the unlock, failed
silently via `|| true`, and the mode never propagated.

**Pattern — mode-override map enforced inside the per-file loop, after unlock
+ copy, unconditionally (not gated on the change detector):**

```bash
declare -A MODE_OVERRIDES=(
  ["${CORTEX_DEPLOY_HOME}/hooks/post-merge"]="700"
)

# ...inside check_each_mapped_file(), after the copy loop:
for _mode_dest in "${!MODE_OVERRIDES[@]}"; do
  _mode_val="${MODE_OVERRIDES[$_mode_dest]}"
  if [[ -f "$_mode_dest" ]]; then
    chmod "$_mode_val" "$_mode_dest" 2>/dev/null \
      || warn "  mode override failed for ${_mode_dest/$HOME/~}"
  fi
done
```

- **`declare -A` is safe here** because cortex-update.sh re-execs to brew bash
  ≥4 on macOS (the script has a bash-version guard at the top).
- **Test the full sequence, not the isolated step.** A lone `chmod 700` on a
  locked file correctly fails with "Operation not permitted" — that failure is
  the bug being fixed, not a test artifact. Verify unlock → chmod succeeds →
  re-lock, exactly as the deploy loop does. (Piping the unlock through
  `head`/`tail` can SIGPIPE-kill the unlock loop mid-way and produce a false
  "chmod failed" — capture output to a variable or file instead.)

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

**Assert the depth from the script's own test.** Copy the real script into a
fabricated repo tree (`<tmp>/ops/scripts/lib/<name>.sh` plus stub
prerequisites) and run it there: a root resolved one level short immediately
builds paths like `<tmp>/ops/ops/install/requirements.txt` and fails, instead
of surviving to a peer host where the doubled segment is the only symptom.

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

### Bound the ITEM COUNT, not just the per-item cost

Replacing a loop with a pipeline fixes the cost PER ITEM; it does nothing about an UNBOUNDED item
list. A step that runs one command per entry (a `git diff` per changed path, a probe per row, a
`stat` per file) is fine at five items and takes minutes at a thousand — and the list is usually
not yours to bound: a push range, a directory listing, a remote's file list, a table's row count.
Cap it explicitly and say so:

```bash
MAX_ITEMS=20
for p in "${items[@]:0:$MAX_ITEMS}"; do ... done   # and disclose "checked N of M"
```

Two rules that keep the bound honest: the cap must be DISCLOSED in the output (a silent truncation
reads as coverage of everything), and the branch that consumes the capped list must be ADVISORY — a
scan that can only see the first N items must never be the thing that authorises or blocks an
action. A bound is a product decision, not an optimisation: if the full list really must be
processed, batch it into ONE command instead of enlarging N.

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

### BRE alternation `\|` is GNU-only — use ERE `|` for macOS

**Plain `grep` uses BRE (Basic Regular Expressions), where alternation is `\|` — a GNU extension. BSD grep (macOS) treats `\|` as literal characters, so the alternation silently NEVER matches.** The filter then passes everything through instead of filtering — the failure is silent, not an error.

```bash
# ❌ GNU-only — on macOS/BSD these match NOTHING (literal backslash-pipe), so
#    the intended exclusion silently fails and binary bytes reach scanners
STAGED_FILES=$(git diff --cached --name-only | grep -v '\.svg$\|\.png$\|\.jpg$')

# ✅ POSIX ERE — alternation works on both GNU and BSD
STAGED_FILES=$(git diff --cached --name-only | grep -vE '\.(svg|png|jpg)$')
```

**Real bug (2026-08-12, fixed `0f6acddf`):** `pre-commit-score`'s STAGED_FILES filter used BRE `\|` alternation (`'package-lock\.json\|yarn\.lock\|pnpm-lock\.yaml'` and `'\.svg$\|\.png$\|\.jpg$\|\.jpeg$\|\.gif$\|\.ico$'`). On GNU/Linux the exclusions worked; on macOS/Titus they treated `\|` literally, so real image filenames were never excluded, binary bytes hit the scanners, and `adversarial-verify.py` crashed with `UnicodeDecodeError` — hard-blocking every image commit. The fix was POSIX ERE `grep -vE` with a character-class alternation group. Sibling crash-class fix `e399b19c` hardened all `open()+readlines()` sites with `errors="replace"` — check sibling paths for the same flaw class, not just the reported line.

**Rules:**
- Never write alternation as `\|` in BRE patterns — use `grep -E` (ERE) whenever a pattern needs `|`.
- Same trap applies to `sed` BRE (`s/a\|b/.../` is GNU-only; use `-E`), `awk` is ERE by default (safe).
- Verify portability with a BSD-semantics simulation (`grep -F` treats the pattern literally, mimicking BSD's `\|` behavior) or test on the actual macOS host.
- When a filter "works on Linux but breaks on macOS," grep the whole tree for sibling instances of the same BRE `\|` class before fixing one.

## Resolving an Interpreter by CAPABILITY, Not by Path

A script that picks its own `python3` must test the **module** it needs. A path says
nothing about what an interpreter can import, and the usual fallback is the one
interpreter known to lack it:

```bash
# ❌ the guard never fires: the FILE exists, the MODULE does not
PY_CMD="${HOME}/.hermes-cortex/venv/bin/python3"
[[ -x "$PY_CMD" ]] || PY_CMD="python3"        # and this python3 lacks it too
```

```bash
# ✅ test the capability; try candidates in preference order; refuse loudly
candidates() {
  [[ -n "${PYTHON:-}" ]] && printf '%s\n' "$PYTHON"
  [[ -n "${HERMES_VENV:-}" ]] && printf '%s\n' "${HERMES_VENV}/bin/python3"
  printf '%s\n' "${HOME}/.hermes-cortex/venv/bin/python3"        # the FLEET venv, first
  printf '%s\n' "${HOME}/.hermes/hermes-agent/venv/bin/python3" # last resort: migrating away
  command -v python3 2>/dev/null || true
}
tried=""
while IFS= read -r py || [[ -n "$py" ]]; do
  command -v "$py" >/dev/null 2>&1 || continue
  case " ${tried} " in *" ${py} "*) continue ;; esac   # dedupe repeated candidates
  tried="${tried} ${py}"
  "$py" -c 'import importlib, sys; importlib.import_module(sys.argv[1])' yaml \
      >/dev/null 2>&1 && exec "$py" "$@"
done < <(candidates)
echo "COULD NOT VERIFY: no interpreter can import yaml; tried:$tried" >&2
exit 3
```

- Pass the module name as **ARGV**, never interpolated into the `-c` string.
- **Probe in a CLEAN environment — an inherited `PYTHONPATH` decides for you.** Measured on esther
  2026-10-13: the agent runtime exports a Python 3.14 site-packages from a Hermes-managed install
  environment, and it lands AHEAD of the target venv's own packages. Every capability probe then
  judged the WRONG packages: the fleet venv — which imports `mcp` perfectly — read as missing it,
  the deploy reported a false `fleet venv cannot import the declared set`, and the resolver
  announced `COULD NOT VERIFY — no interpreter can import 'mcp'` about a host that had it in two
  venvs. Run probes AND payloads as `env -u PYTHONPATH -u PYTHONHOME "$py" …` (POSIX, so Linux +
  macOS), and SAY what you ignored — a variable silently dropped by the tooling is how the venv
  took the blame for the caller's environment.
- **Fix the CLASS, and pin the enumeration with a committed test.** A probe fixed at one call site
  is a claim about that site. `rg -n "-c [\"']import" ops/` (and any other interpreter form that
  makes a DECISION — a `yaml.safe_load` validator counts) before saying the fix is complete; then
  commit the enumeration as a sweep test that FAILS when a new deciding probe appears without a
  clean environment, with any exemption stated and justified (stdlib imports are exempt: a foreign
  site-packages is where THIRD-PARTY packages live, and it cannot change `sys.version`). The sweep
  earns its keep immediately — it caught the fallback probe written into the fix minutes later.
- Give "cannot resolve" its **own exit code** (`3`), never a generic failure: a caller that
  reports it as a failed test blames the payload for a host dependency it never measured.
- **A `python -c 'import X'` probe is only HALF the class: cover `python3 script.py` too.** The
  other half is a shell script that RUNS a python FILE. Same environment dependency, buried one
  level deeper, and the probe sweep cannot see it. Rule: the interpreter choice matters only when
  the file imports a THIRD-PARTY module — a stdlib-only file is interpreter-independent, so
  flagging it just teaches ceremony. Pin it with a committed sweep that, for every `python3 *.py`
  in the repo's shell scripts / units / timers, parses the target with `ast` and fails when a
  non-stdlib import is present without the arbiter. Two things make such a sweep honest: (1)
  resolve LOCAL modules (they are not third-party) and EXPAND them transitively — the finding in
  this repo (`yaml`) sat behind a package import, so a check that reads only the entry file calls
  a yaml-importing program stdlib-only; recognise all three local shapes in use, including a
  dir-of-modules on `sys.path` with no `__init__.py`. (2) Fix every site rather than
  allowlisting: a guard with zero exemptions is worth more than one with a list.
- **A failing run that pipes its output through `grep` fails SILENTLY.** A re-runnable evidence
  script invoked `cortex-doctor.py 2>&1 | grep -i SOUL`: when the interpreter lacked `yaml` the
  traceback was filtered away and the section printed EMPTY — which reads as "nothing to report",
  not as a failure. Prefer a resolved interpreter; and when a pipeline must filter, keep the exit
  status (`PIPESTATUS[0]`) or capture to a variable so a crash cannot masquerade as an empty
  result.
- **Never quote a pipeline's status as the command's.** `cmd | head -1; echo $?` prints head's
  status. Capture bare (`cmd 2>err; rc=$?; head -1 err`) — a "verified" rc that came from the
  filter is the same class of false signal as a check that reports on something it never measured.
  `PIPESTATUS` looks like the fix and is a second trap: it is reset by EVERY command, so any `echo`
  between the pipeline and the read leaves it empty — the artifact then prints `rc=` and reads as
  zero-or-unknown. When the output must also be trimmed, write it to a file and read the status in the
  very next statement: `cmd > out 2>&1; rc=$?; tail -3 out`.
- **A comment promising a guard is not a guard.** A pre-commit audit's comment said "only flag NEW
  scripts" while the code flagged any staged script lacking a `register()` line — every edit to an
  unregistered (e.g. evidence) script fired a false advisory, which trains readers to ignore the
  audit. Read the code, not the comment, and exempt by directory with the reason stated.
- The fleet already ships this as
  **`ops/scripts/lib/python-with-module.sh <module> <script> [args]`** (add `--print <module>`
  when a caller only needs the path). Reuse it rather than writing another copy — it is
  registered in `cortex-update.sh` and deploys to `scripts/lib/`.
- `PYTHON=` is the escape hatch an operator reaches for; honour it first.
- **Declare ONE interpreter; never let each caller re-derive a path.** A rule copied into seven
  scripts is seven chances to write it differently, and the copies WILL disagree — one check calls
  a venv healthy while another warns about it, and a validator blames a file. Provision a per-host
  declaration (`CORTEX_PYTHON` in `~/.hermes-cortex/agent.env`; the deploy writes the default) and
  have the arbiter read it before its built-in order, after `PYTHON=`. Two rules make a declaration
  safe: **never overwrite an operator's value** (a host may legitimately point elsewhere — a
  Homebrew python on macOS, a different venv; prove it by deploying twice and asserting the file
  still holds exactly one such line), and **treat it as a promise** — when the declared interpreter
  cannot import the module asked for, NAME it in the failure output rather than falling through
  silently, or a wrong declaration hides exactly as the old PATH-pick hid a missing dependency.
  Report the declaration as a HOST FACT in the doctor (path + a clean-env import check), so "which
  python does this host use?" is one line instead of a re-derived path.

**Resolving an interpreter is half the job — commit the CREATE step too.** A capability resolver
finds a dependency that ALREADY exists somewhere; if nothing in the repo provisions it, the resolver
is correct on the one host where somebody built it by hand and silently degrades everywhere else
(every file needing that capability then reports NOT RUN, which reads as a clean run). So pair every
resolver with a committed, deploy-registered other half:

- a command that CREATES what the resolver looks for — idempotent **by import**, not by metadata or
  by an installer's exit code — running the repo's DECLARED dependency set, the canonical venv, and
  the repo's supply-chain age gate;
- an exit-code contract that keeps the outcomes apart: `0` usable (print the interpreter path on
  stdout), `1` refused or installed-but-still-unusable, `3` COULD NOT VERIFY (a prerequisite is
  missing);
- the resolver's failure branch NAMING that command, never just "install X" — a hint that names a
  command the peer host does not have has only moved the gap.

Drive its branches against a FABRICATED repo tree (a copy of the real script beside stub
prerequisites, `HOME` redirected to a temp dir) so the age-gate-refused, unusable-install and
missing-prerequisite paths are exercised on any host. That an age gate ran BEFORE the installer is
provable only from the installer stub's own log — source order is not evidence.

**Prefer the CORTEX venv (`~/.hermes-cortex/venv/bin/python3`) — it is the venv the fleet runs
its services with** (`cortex-update.sh` registers every MCP server against it). The Hermes venv
is a last resort: fleet tooling should not depend on the tree we are migrating away from.
Ordering only breaks a *tie* — a candidate must still import the module to be chosen, so a
module only the Hermes venv has keeps resolving. Measured on esther 2026-10-13: the cortex venv
imports yaml + mcp (and pytest once installed there); the Hermes venv imports all three; the
Hermes *tools* python imports none. An undated "the cortex venv has no PyYAML" note lived in
this skill and in `tests/test_python_with_module.py`, and a deploy had reordered the two venvs
the other way — a measurement with no date is a claim about the past, so re-measure before
relying on one.

**uv-created venvs have NO `pip` binary.** A uv venv's `bin/` holds only `python*`, so
`<venv>/bin/pip` does not exist and `<venv>/bin/python3 -m pip` fails too. Install with
`uv pip install --python <venv>/bin/python3 <pkg>`, then **verify by importing**
(`<venv>/bin/python3 -c 'import yaml, mcp'`): a venv existing proves nothing about what is
inside it, and one can hold a single package while every caller expects more.

**After changing WHICH interpreter runs a suite, prove it can COLLECT the suite.** A
dependency missing from the preferred interpreter does not fail the run: pytest reports
`collected N items / 1 error` and still prints a pass count for everything else, so the
suite looks green while an entire module silently contributes no tests. Check the class in
ONE pass rather than discovering it module by module:

```bash
"$PY" -m pytest tests/ --collect-only -q 2>&1 | grep -E "ModuleNotFoundError" | sort -u
```

When a module is missing, install it into the FLEET venv (not a private one) so every caller
that resolves to that venv gets it — a dev dependency present in one venv and absent in the
fleet venv is a suite that passes for you and drops tests on a host.

**The runner's own environment can shrink the suite even when the interpreter is right — and
INSTALLING will not fix that one.** A contaminated `PYTHONPATH` shadows the target's packages
instead of leaving an import missing, so the failure looks like an ABI mismatch
(`ModuleNotFoundError: No module named pydantic_core._pydantic_core`) rather than an absent
package. Measured 2026-10-13, same interpreter, same command, only the environment differing:
with the agent session's `PYTHONPATH` inherited it collected **1817 tests with 4 errors**; with
it removed, **1845 with none**. Twenty-eight tests — four whole modules — were absent from every
"N passed" run, and nothing failed, because pytest still prints a count for everything else.

Check the two halves SEPARATELY and compare the COUNT, not just the error lines:

```bash
env -u PYTHONPATH -u PYTHONHOME "$PY" -m pytest tests/ --collect-only -q 2>&1 | tail -2
```

A collected count that changes with the environment IS the finding: the suite is not hermetic,
so every downstream claim resting on it — a pass count, a coverage figure, a "suite is clean"
certificate handed to a peer — is a claim about the caller's environment, not about the code.
Put `env -u PYTHONPATH -u PYTHONHOME` in the test recipe you hand to other agents.

**A guard for this is a decision, not an automatic fix.** A test asserting "the suite collects
with zero module errors" FAILS on every runner that still inherits the environment, so it turns a
shared suite red the moment it lands. Fix the runners/recipe first, or land the guard with the
operator's agreement — never slip a permanently-red test into a repo other agents gate on.

**Do not hand-install module by module — the fleet DECLARES what belongs in the venv and ships
the repairer.** The declared set is `ops/install/requirements.txt` (measured from the repo's own
imports; edit THAT to add a dependency, or the next host never learns about it):

```bash
python3 ops/scripts/manage/fix-cortex-venv.py --check   # what is missing; changes NOTHING (rc=3)
python3 ops/scripts/manage/fix-cortex-venv.py           # install only the missing, then verify
```

It decides by **importing** in the TARGET interpreter (a distribution name is not a module
name: `PyYAML` → `yaml`, `psycopg[binary]` → `psycopg`), prefers `uv`, falls back to the venv's
own pip, and re-checks by import afterwards rather than trusting the installer's exit code.
`cortex-update.sh` reports the venv's state on every deploy, so a host that is short says so
and prints the exact repair command — an agent does not have to discover the gap itself. A
repair run is a manual operational step: record its command in the evidence and let a verifier
assert the resulting STATE non-destructively (versions, import check).

### A verifier must not mutate the thing it measures

A check that installs, upgrades, or reconfigures what it inspects reports on a state it just
changed, and can pass because of its own side effect. Split the two halves:

- The **operational** step (install, migrate, rotate) runs once; record its exact command in
the artifact and label it as the manual step it is.
- The **verifier** asserts the resulting STATE non-destructively — distribution versions via
  `importlib.metadata`, an import check, a collected-test count — and fails when the state is
  wrong.
- **Do not hang a check on a `--dry-run` flag.** Coverage varies by tool and version, and an
  unsupported flag returns non-zero, so a broken-looking check is really an unsupported
  option. Prefer a command that is idempotent by nature (re-running an install reports
  nothing to do) or a read-only query.

## Shipping a Portable Script: Scan the Source, Then Drive the Branches

A script that only has to run on your host is not portable, and "it works here" cannot see the
difference. Before shipping anything other hosts will run — macOS especially, which ships **bash
3.2** and BSD userland — scan the SOURCE for the constructs that break there, and commit the scan as
a test so it cannot creep back:

```
bash 4 only : declare -A, mapfile, readarray, local -n, ${var,,}, ${var^^}, &>>
GNU only    : readlink -f, date -d, grep -P, sed -i without a suffix, sha256sum (macOS: shasum -a 256),
              timeout (macOS: gtimeout — never call `timeout` unconditionally: the script then does not
              run AT ALL on macOS, rather than degrading)
```

Also assert the shebang is `#!/usr/bin/env bash` (a hardcoded `/bin/bash` is the other portability
trap), that the repo root is derived from the script's own location, and that no absolute
`/home/<user>/` path appears. Referring to a fleet install is fine — REQUIRING one is not: assert any
such reference goes through `$HOME`, so the script still runs on a host that has none.

Reading the source is not enough on its own. Drive the REAL script in a CONSTRUCTED environment (a
temp repo, an empty HOME, a stubbed PATH) for the branches your host cannot reach — the absent-tool
path, the fallback path, the could-not-verify path. An untested branch is untested by definition,
and these are exactly the branches that only run where you are not.

**A fallback that does not ANNOUNCE itself is a swapped signal.** A resolver/shortcut fallback that
silently picks a different interpreter makes the run look identical while a different program decides
— it "passes", against the wrong thing. Print which path was used and why the first choice was
skipped (`note: no repo resolver at …; falling back to …`). This matters most when the fallback is the
fallback is the branch a test was meant to stub: a silent fallback let a stub test exercise the REAL
resolver and report success, which is how the missing announcement was found.

**Prove the BRANCH was taken, not just that the script ran.** Driving a constructed environment is
evidence only if the fallback really is the branch under test, and the usual failure is SILENT: a
shim placed first on `PATH` still loses to the real binary, so the run exercises the very path it was
meant to avoid and reports green. Assert the precondition in the same recipe:

```bash
d=/tmp/shim; rm -rf "$d"; mkdir -p "$d"
for t in bash sh git python3 mktemp rm dirname basename; do ln -s "$(command -v $t)" "$d/$t"; done
printf '#!/bin/sh\nexec /usr/bin/timeout "$@"\n' > "$d/gtimeout"; chmod +x "$d/gtimeout"
env PATH="$d" bash -c 'command -v timeout || echo NO-timeout'   # MUST print NO-timeout
env PATH="$d" bash ./script.sh <args>                            # now the fallback IS the branch
```

Two rules make it honest. The narrowed `PATH` must ALSO carry the tools the script itself needs
(dropping one makes it fail for an unrelated reason — a different finding wearing the same red), and
the recipe belongs BESIDE the claim, with the claim scoped to what it proves: "the fallback branch
works" is provable this way on any host; "it works on macOS" is NOT, and asserting that from a Linux
run is the over-claim a reviewer will file. State the un-run platform as unverified rather than
covered by a shim.

**An exit-code comparison must pre-check every binary the wrapper invokes.** A loop that runs
`timeout N python3 <file>` with its output discarded turns a MISSING interpreter into exit 126/127,
which the caller then reads as the file's OWN result — so two shell errors get compared and reported
as agreement or as a difference. Resolve both the timeout binary and the interpreter up front and
refuse loudly when either is absent (`exit 2`, named); then every code the loop sees can only have
come from the payload, and "no difference" means something.

**A shared guard must not encode one repo's NUMBERS.** A collection guard asserting "more than 1000
tests" was true only of the repo it was written in; in a smaller or unrelated repo it fails a HEALTHY
environment, which teaches readers to ignore the guard. Assert the property that must hold anywhere
(no module errors, more than zero collected) and keep the repo's own size out of it.

**A runner handed only FLAGS tests far more than you asked.** `pytest` with no PATH collects the
CURRENT DIRECTORY: from a repo root that is `.git`, the deploy trees and every vendored copy, and it
can sit silent for minutes (measured: past 400 s with no output, killed by a timeout). A wrapper that
passes `"$@"` through must supply the suite when the caller names no selection, and must still
propagate the runner's OWN rc so an unresolvable path is a failure rather than a green zero:

```bash
case " $* " in
  *" tests"*|*" tests/"*|*"/*"*|*"::"*|*".py"*) : ;;   # a selection was named
  *) set -- "$@" tests/ ;;                                # flags only: add the suite
 esac
```

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

7. **The exit code of a subprocess is not evidence the thing landed.** An installer that runs `pi install … >/dev/null 2>&1`, `npm i … >/dev/null`, or any fetcher and then keys success on `$?` reports a green line for a no-op: the declaration can be written while nothing arrives. Two rules, both cheap:

   ```bash
   # ❌ output discarded, success read off rc alone
   if "$LAUNCHER" install "$PKG" >/dev/null 2>&1; then echo "✓ installed $PKG"; fi

   # ✅ capture the output, assert the ARTIFACT, report what the tool said
   LOG="$(mktemp "${TMPDIR:-/tmp}/install.XXXXXX")"
   if "$LAUNCHER" install "$PKG" >"$LOG" 2>&1; then
     if [[ -d "$PKG_DIR" ]]; then                # the effect, not the rc
       echo "  ✓ installed $PKG"; last="$(tail -n 1 "$LOG")"
       if [[ -n "$last" ]]; then echo "    launcher: $last"; fi
     else
       echo "install: $LAUNCHER exited 0 but $PKG_DIR is absent" >&2
       tail -n 20 "$LOG" >&2; exit 1
     fi
   else
     rc=$?; echo "install FAILED (rc=$rc)" >&2; tail -n 20 "$LOG" >&2; exit 1
   fi
   ```

   - **Discarding a subprocess's output in its failure path is a swallowed error**: the message the operator needs (npm 404, auth failure, a yanked version) is exactly what got thrown away, and the script exits 1 telling them to re-run it by hand to find out.
   - **`[[ -n "$x" ]] && echo …` as a bare statement is a `set -e` trap** — an empty value makes the whole AND-list return 1 and kills the script right after a *successful* install. Use `if [[ -n "$x" ]]; then …; fi`.
   - Assert the artifact for the same reason the doctor's checksum fails: a declaration in a config file and the thing on disk are two different facts, and only the second one makes the capability work.

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
| **Fence counting: `grep -c '^```'` vs strip-based count** | Strip-based counting (`line.strip().startswith("```")`) includes INDENTED fences (inside code blocks) → phantom imbalance; a file that reads 1080 by strip-count is 885 line-starting and BALANCED. Appending an EOF closer to a file already even/paired by the line-starting rule flips it to UNBALANCED (the appended fence becomes a NEW orphan opener — llms-full.md 884→885 on 2026-08-02). | Count with `grep -c '^```'` or python `line.startswith("```")` — NEVER `strip().startswith()`. Verify with sequential pairing (open/close stack), not just parity. Only append a closer when the file's LAST line-starting fence is genuinely unclosed. |
| `declare -A` (associative arrays) on macOS | `declare: -A: invalid option` on macOS (ships bash 3.2, needs 4+) | Use parallel indexed arrays: `ARR_KEYS=() ARR_VALS=()` + numeric-index loop. Or use a Python script for complex maps. |
| `set -e` + `((var++))` | Script exits silently mid-function when counter is 0 | Use `var=$((var + 1))` or `: $((var++))` |
| `\$` in double-quoted strings | Literal string `$HOME` passed instead of expanded path | Remove `\` before `$`: `"$HOME"` not `"\$HOME"` |
| Bare `if` in mawk | `awk: line 2: syntax error at or near if` on Ubuntu | Wrap awk body in `{ }` |
| Missing `timeout` on macOS | `command not found: timeout` | Fall back to `gtimeout`, then no timeout |
| **`A && B \|\| C` — the `$?` seen by `C` is the FAILED command's status, not the assignment's** | A review or an agent reads the one-liner as "always 0, so the guard is dead" and rewrites working code | `f() { return 3; }; out=$(f 2>&1) && r=0 \|\| r=$?; echo $r` prints `3`. TEST the idiom before editing code a claim contradicts; an explicit `if/else` rewrite is fine as a clarity change, but call it that instead of a bug fix |
| **A wrapper's exit code read as the payload's** | `timeout N python3 file` with output discarded: a missing interpreter returns 126/127, which the tooling reports as the test's own result | Resolve the timeout binary AND the interpreter before the loop, refuse loudly if either is absent, then the codes can only be the payload's |
| `grep -P` on macOS | `grep: invalid option -- P` | macOS grep doesn't support Perl regex; use `grep -E` or install `ggrep` |
| **BRE `\|` alternation on macOS** | Filter silently matches NOTHING on BSD grep — exclusions never apply, binary bytes reach scanners (pre-commit-score image filter, 2026-08-12) | Use `grep -E` ERE alternation `(a|b)` — POSIX, works on GNU + BSD |
| **Per-item loop with grep inside** | Script takes minutes for 2000 items | Replace with batch pipeline — 5 grep calls total |
| **grep ADDED from /dev/stdin** | Success message for an operation never fires, but no error either | Capture output in a variable and check it: `[[ "$_var" == *"ADDED"* ]]` |
| **Counter var overlap (dry-run vs real)** | Summary shows misleading counts | Use separate vars: `WOULD_CREATE` vs `CREATED` |
| **Mixed formatting for positional-arg functions** | Hard to audit — must count empties to understand args | Standardize all calls to multi-line, one field per line |
| **Missing script existence path** | "Script not found" warning scrolls past silently | Check all possible locations: `scripts/`, repo source, `~/.local/bin/` |
| **Appending to a per-host env/state file with `>>` onto a file with no trailing newline** | Two vars join onto ONE line (`AGENT_NAME=mosesCORTEX_PYTHON=...`) — a parser that reads `^NAME=` lines returns the WHOLE garbage string as one value, so identity/role resolution fails (a task-db CRUD role resolves to a nonsense name) and every DB/RLS/connectivity probe FAILs for a reason that looks environmental | Before `>>`-appending any line, ensure a trailing newline: `[[ -s "$f" ]] && tail -c1 "$f" | grep -q '\n' || printf '\n' >> "$f"`, or rewrite the file with newline-terminated lines. The durable fix is the APPENDER guaranteeing a final newline; if you repair a corrupted file, end it with `\n` so the next append is clean |
| **Interpreter chosen by path existence** | `No module named X` although X is installed — under a DIFFERENT interpreter; an `[[ -x $VENV/bin/python3 ]]` guard never fires because the file is there | Test the CAPABILITY (`"$py" -c 'import X'`), try candidates in order, `exit 3` = could not verify; never silently fall back to a `python3` known to lack it |
| **An inherited `PYTHONPATH`/`PYTHONHOME` around a capability probe** | A HEALTHY venv reads as broken — or a bare python as capable — because a foreign site-packages shadows the target's own. Measured: the fleet venv (which imports `mcp` fine) reported as missing it, and the resolver claimed no interpreter on the host could import `mcp` at all | Probe and run with `env -u PYTHONPATH -u PYTHONHOME`; print what you ignored. A venv's correctness must not depend on the caller's environment |
| **A checker that cannot read its input reports the FILE as broken** | A valid YAML manifest reported as "parse issue" because the validating script used a bare `python3` with no `yaml` — the checker blamed the artifact for its own missing dependency, and a task got filed against a file that was never wrong | A checker with no parser has NO VERDICT. Resolve an interpreter that can import the dependency (the arbiter above), and when none can print `COULD NOT VERIFY … not checked` — never a negative verdict about the artifact. Applies to every lint/validate step that shells out for its parser |
| **`[[ -n "$x" ]] && cmd` as a bare statement under `set -e`** | The script exits 1 at that line whenever the test is false — e.g. right after a successful install whose last output line is empty, so the failure reads as "the install broke" | Use `if [[ -n "$x" ]]; then cmd; fi`. The `&&` form is only safe inside a condition (`if [[ … ]] && cmd; then`) or with `|| true` |
| **Subprocess output discarded in the failure path** | `cmd >/dev/null 2>&1` under an `if` reports "FAILED" with the reason (npm 404, auth, yanked version) thrown away; the operator must re-run it by hand to learn what the script already knew | Capture to `mktemp` and print `tail -n 20` plus the rc on failure; on success print the tool's own last line and assert the ARTIFACT exists (see installer audit item 7) |
