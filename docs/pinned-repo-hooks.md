# Pinned Repo Hooks — Refresh + Guard Carve-Out

**Status:** Shipped 2026-08-05 (`527e651a`), Titus audit follow-up.

## Problem

`pin_repos_with_own_hooks()` (cortex-update.sh) preserves repos that ship
their own git hooks by setting a repo-local `core.hooksPath` to the repo's
own `.git/hooks`. It pinned the path but **never refreshed the hook files** —
pinned repos kept stale copies (Jul 24 generation) that predated the
mandatory adversarial gate (faa0e929/72d6cdc3). Commits in those repos got
score-logging but **no adversarial verification** (Titus audit 2026-08-05: 9
repos on macOS, `grep -c adversarial = 0`).

## Fix (three parts + one critical addition)

1. **`refresh_pinned_hook_files()`** — after pinning, copies the 4 cortex
   hooks (pre-commit-score, pre-push-pull, post-commit-audit, post-push-audit)
   from deployed source into the repo's own hooks dir. Only files carrying
   the cortex banner (`Git <type> hook`, ASCII match for macOS locale
   safety) are refreshed; **foreign hooks are preserved** (vllm pre-commit
   framework shim, bespoke deploy hooks). Missing hook files get the gate
   installed.

2. **Crawl exclusions** — `*/Library/*` and `*/node_modules/*` pruned from
   the pin crawl: macOS `~/Library/Containers` is a ~1m20s crawl per deploy
   (Aug 4 incident wedged it 5h08m); node_modules holds thousands of vendored
   `.git` dirs that must never be pinned.

3. **Doctor check `Pinned hooks fresh`** (7c) — for every repo with a local
   `core.hooksPath`, compares each cortex hook file against the deployed
   source with `_content_md5()` (strips the SOURCE header). FAIL on drift
   with remediation hint `cortex-update.sh --force`. Foreign hooks skipped.

4. **⚠️ Guard carve-out (critical — discovered during verify)** — the
   deployed pre-commit/pre-push hooks fail CLOSED when `core.hooksPath !=
   ~/.hermes-cortex/hooks` (5ab54547). Pinned repos exist precisely because
   their hooksPath points at their own dir — refreshing the full hooks into
   them would have blocked **every commit**. The guard now passes when the
   hooks dir carries any cortex-managed hook (governance IS running there);
   it still fails closed when hooksPath points at a dir with no cortex hooks
   (the original bypass tripwire).

## Why the carve-out is safe

The guard's own comment states its purpose: *"The REAL danger is when
hooksPath points elsewhere entirely, meaning NO governance hooks run at
all."* A pinned repo with refreshed cortex hooks HAS governance running —
the carve-out accepts exactly that state. A repo pointing hooksPath at an
attacker-controlled dir with no cortex hooks still blocks.

## Verify (all three, done on Linux 2026-08-05)

1. Scratch repo with stale cortex hook → refreshed to byte-match deployed,
   adversarial gate present (10 hits), commit passes the hooksPath guard
2. Repo with foreign vllm shim → refresh skips it, hash unchanged
3. Doctor: FAIL on stale (`36f9a960 != 13bbebff`) → refresh → PASS
   ("all 4 pinned hook file(s) match deployed source")

## Rollout

Deployed via `cortex-update.sh`; the refresh runs automatically on every
deploy for all pinned repos on every host (Linux + macOS). No manual action
per repo.
