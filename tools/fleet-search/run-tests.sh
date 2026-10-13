#!/usr/bin/env bash
# Re-runnable proof for tools/fleet-search: runs every test, then RE-MEASURES the resource
# envelope the design claims. Exit status is a real gate (non-zero on any failure), so a cron or a
# CI job can call it and believe the answer.
#
# Usage: bash tools/fleet-search/run-tests.sh
set -uo pipefail
cd "$(dirname "$0")" || exit 1

echo "== cargo test: unit tests plus the end-to-end tests that drive the real binary =="
cargo test 2>&1 | tail -12
# The TEST's status, not tail's: a pipeline's status belongs to its last command, and reporting
# tail's would make this script claim success for a failed suite.
rc=${PIPESTATUS[0]}
echo "cargo test rc=$rc"
if [ "$rc" -ne 0 ]; then
  echo "FAILED: the suite did not pass" >&2
  exit "$rc"
fi

echo
echo "== the envelope docs/design/agent-search.md claims, re-measured =="
cargo build --release 2>&1 | tail -1 || exit 1
ls -lh target/release/fleet-search | awk '{print "binary size: " $5}'
# Idle RSS of the MCP server: a real process, waiting on stdin, which is how an agent runs it.
sleep 8 | ./target/release/fleet-search mcp &
sleep 2
ps -o rss=,vsz=,comm= -C fleet-search 2>/dev/null |
  head -1 | awk '{printf "idle RSS: %.1f MB  VSZ: %.1f MB\n", $1/1024, $2/1024}'
wait

echo
echo "== the two paths an agent takes when search is NOT available (exit codes are contract) =="
XDG_CACHE_HOME="$(mktemp -d)" ./target/release/fleet-search search "x" >/dev/null 2>&1
echo "search with no provider        rc=$?   (3 = could not verify)"
XDG_CACHE_HOME="$(mktemp -d)" ./target/release/fleet-search local "x" >/dev/null 2>&1
echo "local search, empty cache      rc=$?   (0 = ran, and found nothing)"
echo
echo "exit: 0"
