# macOS Portability of the Fail-Closed Pre-Commit Hook (2026-08-03)

Incident context: after converting the score-cycle missing-scorer path from
`warn + exit 0` (bypass) to `exit 1` (fail closed), the hook worked on Linux
but would have hard-blocked EVERY commit on Titus (macOS) for two reasons.
Both are fixed by making the scorer findable and the timeout invocation
portable.

## Problem 1: macOS has no `~/.local/bin` in PATH

`command -v score-cycle` fails on macOS even when loop-governance is installed.
The search loop previously only tried PATH + `~/.local/bin/score-cycle`.

Fix: add the canonically-deployed scorer path as a candidate. cortex-update.sh
registers it to the SAME location on both OSes:

```bash
for candidate in score-cycle ~/.local/bin/score-cycle \
    "$HOME/.local/bin/score-cycle" \
    "$HOME/.hermes-cortex/tools/loop-governance/score_cycle.py"; do
  if resolved=$(command -v "$candidate" 2>/dev/null); then
    SCORE_CYCLE="$resolved"
    break
  fi
done
```

Verify with an emptied PATH (proves the deployed-path candidate, not PATH):

```bash
PATH=/nonexistent bash -c '...search loop...; echo "SCORER:[${SCORE_CYCLE}]"'
# → SCORER:[$HOME/.hermes-cortex/tools/loop-governance/score_cycle.py]
```

## Problem 2: macOS has no `timeout` (needs `gtimeout`)

The scoring invocation was `timeout 30 "$PYTHON_BIN" "$SCORE_CYCLE"` — fails
on macOS (command not found → the `|| { hard block }` fires → every commit
blocked even with the scorer present).

Fix: resolve the timeout binary before invoking:

```bash
_TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
  _TIMEOUT_BIN="timeout 30"
elif command -v gtimeout >/dev/null 2>&1; then
  _TIMEOUT_BIN="gtimeout 30"
fi
SCORE_OUTPUT=$($_TIMEOUT_BIN "$PYTHON_BIN" "$SCORE_CYCLE" --task ... )
```

Behavior matrix (live-tested with a fake `gtimeout` on an emptied PATH):
- Linux (timeout present): `RESOLVED:[timeout 30]`
- macOS + coreutils (gtimeout only): `RESOLVED:[gtimeout 30]`
- macOS without coreutils (neither): `RESOLVED:[]` → unbounded run; the
  `||` hard-block still guards a genuinely failing scorer.

Test caveat: when simulating "no timeout", do NOT set PATH to a dir without
bash — use the explicit interpreter `/bin/bash` and control what the SCRIPT
sees via the env PATH only.

## bash 3.2 compatibility

macOS ships bash 3.2. Safe in this hook's edits: `for-in`, `command -v`,
`[[ -z ]]`, `$(...)`, `if/elif/fi`. Already-present constructs that are ALSO
3.2-safe (do not "fix"): `<<<` herestrings, `[[ =~ ]]`, arrays.
NOT safe (check the whole hook, not just your edit): `grep -P`, `mapfile`/
`readarray`, `${var,,}` case conversion, `&>>`.

## Deploy + verify cycle (both OSes)

1. `bash -n ops/scripts/pre-commit-score` (repo + deployed copy)
2. Commit through the RUNNING hook (exercises scoring + adversarial + self-test
   live; watch for `📊 score-cycle:` in output)
3. `git pull --rebase origin main` then `git push origin main`
4. `bash ops/scripts/cortex-update.sh` (purges your governance
   lock — re-acquire with `begin_change` after)
5. Verify deployed == repo: `diff <(sed '1,2d' ~/.hermes-cortex/scripts/pre-commit-score) <(sed '1,2d' ops/scripts/pre-commit-score)`
6. Grep deployed copy for the fail-closed block + `gtimeout` + the
   deployed-path candidate; confirm scoring anchors still present
   (`SCORE_OUTPUT=`, `ALL_CODE_FILE=`, `PREV_FILE=`, `SCORE_STDERR`).
