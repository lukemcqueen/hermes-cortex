#!/usr/bin/env bash
# migrate-home-dirs.sh — guarded local-directory rename with transition symlink.
#
# Backs the local-dir migration plan (docs/evidence/rename-local-dirs-plan-2026-11-03.md,
# cycle 14077, ADV-14077-5/4). Renames each EMPTY-TARGET source to its
# steadfaste-fleet target and immediately lays an old-path -> new-path
# transition symlink.
#
# Safety (set -euo pipefail): preflights target absence so a POSIX `mv` (no
# -T) can never nest the source, refuses to run inside a target, treats an
# already-symlinked source or target as already-handled, and rolls BACK a
# failed `ln` so a failure never leaves the old path missing. Idempotent +
# re-runnable: any already-migrated pair is a no-op. POSIX-ish on purpose
# (no GNU `mv -T`/`--`) so it runs on BOTH Linux and macOS BSD.
set -euo pipefail

PAIRS=(
  "${HOME}/hermes-cortex|${HOME}/steadfaste-fleet"
  "${HOME}/.hermes-cortex|${HOME}/.steadfaste-fleet"
)

fail() { echo "migrate-home-dirs: ERROR: $*" >&2; exit 1; }

# do not run from inside a source dir we are about to move
case "$PWD" in
  "${HOME}/hermes-cortex"|"${HOME}/.hermes-cortex"|"${HOME}/steadfaste-fleet"|"${HOME}/.steadfaste-fleet")
    echo "migrate-home-dirs: move to a stable workdir before running (cwd=$PWD)"; exit 1 ;;
esac

for pair in "${PAIRS[@]}"; do
  src="${pair%%|*}"; tgt="${pair#*|}"

  [ -e "$src" ] || [ -L "$src" ] || { echo "migrate-home-dirs: skip $src (absent)"; continue; }

  # already migrated: src is a symlink to tgt, or src is absent and tgt exists
  if [ -L "$src" ] && [ "$(readlink "$src")" = "$tgt" ]; then
    echo "migrate-home-dirs: skip $src (already -> $tgt)"; continue
  fi
  if [ ! -e "$src" ] && [ -e "$tgt" ]; then
    echo "migrate-home-dirs: skip $src (absent; target $tgt present)"; continue
  fi

  # a symlink at src that points somewhere OTHER than tgt is a leftover from a
  # partial/failed migration — refuse rather than let mv act on the symlink
  if [ -L "$src" ] && [ "$(readlink "$src")" != "$tgt" ]; then
    fail "source $src is a symlink to $(readlink "$src") (expected $tgt); resolve manually"
  fi

  case "$src" in "$tgt"/*) fail "source $src is inside target $tgt" ;; esac
  case "$tgt" in "$src"/*) fail "target $tgt is inside source $src" ;; esac
  [ "$src" = "$tgt" ] && { echo "migrate-home-dirs: skip (same path)"; continue; }

  # a leftover symlink at the target must not cause mv to nest the source
  if [ -L "$tgt" ]; then
    echo "migrate-home-dirs: remove stale target symlink $tgt"
    rm "$tgt"
  fi
  [ -e "$tgt" ] && fail "target $tgt already exists as a real dir; refusing to nest"

  # target is absent here, so a POSIX `mv src tgt` renames (never nests)
  mv "$src" "$tgt" || fail "mv failed for $src -> $tgt"
  if ! ln -s "$tgt" "$src"; then
    if mv "$tgt" "$src" 2>/dev/null; then
      fail "ln -s failed for $src; rename rolled back"
    else
      fail "ln -s failed for $src AND rollback mv failed (target remains at $tgt); resolve manually"
    fi
  fi
  echo "migrate-home-dirs: $src -> $tgt  (symlink $src -> $tgt)"
done

echo "migrate-home-dirs: done"
