# Bash Pitfalls — Common Patterns That Fail Silently

Collected from real debugging sessions. These are patterns that look correct
but mask failures.

## `$(cmd) || true` Masks Exit Codes

```bash
# WRONG — always sets $? to 0
output=$(python3 scanner.py) || true
exit_code=$?   # Always 0, even if scanner failed

# RIGHT — capture before the || true
set +e
output=$(python3 scanner.py)
exit_code=$?
python3 scanner.py > /tmp/out.txt 2>&1 || true
# Alternative: temp file approach (works with set -e)
tmp=$(mktemp)
set +e
python3 scanner.py > "$tmp" 2>&1
exit_code=$?
output=$(cat "$tmp")
rm -f "$tmp"
set -e
```

**Why it happens:** `$(cmd) || true` sets `$?` to the exit code of `|| true`,
which is always 0. The subshell's exit code is swallowed.

**Where it bites:** Verification scripts that check scanner/validator exit codes.
The script always reports PASS regardless of actual result.

## `set -e` + Subshells = Surprising Behavior

```bash
set -e
python3 fail.py     # Script exits here — correct
output=$(python3 fail.py)  # Subshell exits, BUT outer script continues!
```

**Why:** `set -e` is disabled inside `$()` — the subshell inherits `-e` but the
outer script doesn't see the subshell's non-zero exit.

**Fix:** Use `set +e` / `set -e` wrapping for explicit control, or check `$?`
after the subshell.

## `grep -q` in `set -e` Pipelines

```bash
set -euo pipefail
if grep -q pattern file; then ...  # OK, if handles exit 0/1
grep -q pattern file                # DANGER: exits 1 on no match → script dies
```

**Fix:** Always use `|| true` or wrap in `if`:

```bash
grep -q pattern file || true        # OK, continues on no match
found=$(grep -c pattern file)       # Better: always returns count (0 = no match)
```

## `--exclude-dir` vs `--exclude` in grep

```bash
grep -rn pattern --exclude-dir=stale-ref-watchdog.sh   # WRONG: --exclude-dir only works on directories
grep -rn pattern --exclude=stale-ref-watchdog.sh       # RIGHT: --exclude for file globs
grep -rn pattern --exclude-dir=.venv                   # RIGHT: --exclude-dir for directories
```

`--exclude-dir` only filters directories by name. To filter out a specific file,
use `--exclude` (glob pattern on basename).

## Path Globbing in Grep Include Flags

```bash
grep -rn pattern --include='*.py' --exclude-dir=.git src/  # Works
grep -rn pattern src/ --include='*.py'                      # Works but order matters with some versions
```

Always put `--include`/`--exclude` flags BEFORE the target path argument.
Some grep versions silently ignore them if placed after.
