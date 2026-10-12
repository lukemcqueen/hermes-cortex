#!/usr/bin/env bash
# make-evidence.sh — produce standard, small, runnable, hash-checkable evidence.
#
# WHY (2026-10-12): cycle 12307 spent six rounds with the self-adversarial review on
# evidence the review's material window could not show and the worker had sized by
# trial and error. The fix was partly the window (see mcp-servers/loop-gov-mcp.py
# `_bound_per_file`), and partly this: EVIDENCE SHOULD KNOW ITS OWN SHAPE. Every file it
# writes carries the exact command that made it, the command's OWN exit status (captured
# bare, never a pipe's), the timestamp, and a sha256 of itself — so a reviewer can ask a
# later reader to re-run one command and compare, instead of trusting a transcription.
#
# Usage:
#   make-evidence.sh <out-file> -- <command...>          # run command, write evidence
#   make-evidence.sh --verify <out-file>                 # recompute and compare its sha256
#
# The written file stays under ~600 bytes of header + the command's output (truncated to
# a sane cap), which is the size that fits the review window whole. Output beyond the cap
# is NOT silently dropped: the last line records how many bytes were omitted and the
# command to reproduce the full run.
set -uo pipefail

MAX_BODY=12000
H="$(cd "$(dirname "$0")/.." && pwd)"   # repo root (ops/scripts/..)

if [ "${1:-}" = "--verify" ]; then
  f="${2:?usage: make-evidence.sh --verify <file>}"
  [ -f "$f" ] || { echo "no such file: $f" >&2; exit 2; }
  want=$(grep -m1 '^sha256[: ]' "$f" | awk '{print $2}')
  # The recorded value was computed over the content BEFORE the sha256 line was appended,
  # so verify the same block: everything except that final line.
  got=$(head -n -1 "$f" | sha256sum | cut -d' ' -f1)
  if [ -n "$want" ] && [ "$want" = "$got" ]; then
    echo "OK  $f  (sha256 $got)"
  else
    echo "FAIL $f  recorded=${want:-<none>} actual=$got" >&2; exit 1
  fi
  exit 0
fi

out="${1:?usage: make-evidence.sh [-k] <out-file> -- <command...>}"
keep=0
[ "$1" = "-k" ] && { keep=1; out="${2:?usage: make-evidence.sh [-k] <out-file> -- <command...>}"; shift; }
shift
[ "${1:-}" = "--" ] || { echo "usage: make-evidence.sh [-k] <out-file> -- <command...>" >&2; exit 2; }
shift
[ "$#" -ge 1 ] || { echo "no command given" >&2; exit 2; }

tmp="$(mktemp)"
"$@" >"$tmp" 2>&1
rc=$?                                  # the command's OWN status, captured before any pipe
bytes=$(wc -c <"$tmp")
{ echo "Running: $*"
  echo "rc: $rc"
  echo "when: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  if [ "$bytes" -gt "$MAX_BODY" ]; then
    head -c "$MAX_BODY" "$tmp"
    echo
    echo "... ($((bytes - MAX_BODY)) bytes omitted; re-run the command above for the full output)"
  else
    cat "$tmp"
  fi
} >"$out"
[ -s "$out" ] || { echo "make-evidence: failed to write $out" >&2; exit 1; }
h=$(sha256sum "$out" | cut -d' ' -f1)
printf 'sha256: %s\n' "$h" >>"$out"
rm -f "$tmp"
echo "wrote $out ($(wc -c <"$out") bytes, sha256 $h)"
if [ "$rc" -ne 0 ] && [ "$keep" -eq 0 ]; then
  echo "make-evidence: the wrapped command exited $rc; returning it so a broken run is not a clean artifact (use -k to keep a failing-run transcript)" >&2
  exit "$rc"
fi
exit 0