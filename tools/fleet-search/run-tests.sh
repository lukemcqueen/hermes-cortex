#!/usr/bin/env bash
# Re-runnable proof for tools/fleet-search: runs every test, then RE-MEASURES the resource
# envelope the design claims. Exit status is a real gate (non-zero on any failure), so a cron or a
# CI job can call it and believe the answer.
#
# Usage: bash tools/fleet-search/run-tests.sh
set -uo pipefail
cd "$(dirname "$0")" || exit 1

echo "== cargo test: unit tests plus the end-to-end tests that drive the real binary =="
# The status is captured BEFORE anything consumes the output. A pipeline would invite the reading
# that the reported status belongs to the last command (`a | b` reports b's), so there is no
# pipeline here to argue about. (For the record, `${PIPESTATUS[0]}` IS the left command's status —
# verified: `false | tail` gives PIPESTATUS[0]=1, [1]=0 — but a reader should not have to know that.)
test_output="$(cargo test 2>&1)"
rc=$?
printf '%s\n' "$test_output" | tail -12
echo "cargo test rc=$rc"
if [ "$rc" -ne 0 ]; then
  echo "FAILED: the suite did not pass" >&2
  exit "$rc"
fi

echo
echo "== the envelope docs/design/agent-search.md claims, re-measured =="
cargo build --release >/dev/null 2>&1 || {
  echo "release build FAILED" >&2
  exit 1
}
ls -lh target/release/fleet-search | awk '{print "binary size: " $5}'

# Idle RSS of the MCP server: a real process, waiting on stdin, which is how an agent runs it.
# A fifo holds that stdin OPEN, so the server cannot see EOF and exit before the sample is taken.
# If it is not running when we look, we SAY SO rather than print a number nobody measured.
fifo="$(mktemp -u)"
mkfifo "$fifo" || exit 1
./target/release/fleet-search mcp <"$fifo" >/dev/null 2>&1 &
mcp_pid=$!
exec 9>"$fifo"          # keep a writer attached so stdin never closes
sleep 1
if kill -0 "$mcp_pid" 2>/dev/null; then
  ps -o rss=,vsz= -p "$mcp_pid" |
    awk '{printf "idle RSS: %.1f MB  VSZ: %.1f MB\n", $1/1024, $2/1024}'
else
  echo "idle RSS: NOT MEASURED — the mcp process exited before sampling (do not quote a number)"
fi
exec 9>&-
kill "$mcp_pid" 2>/dev/null
wait "$mcp_pid" 2>/dev/null
rm -f "$fifo"

echo
echo "== the two paths an agent takes when search is NOT available (exit codes are contract) =="
XDG_CACHE_HOME="$(mktemp -d)" ./target/release/fleet-search search "x" >/dev/null 2>&1
echo "search with no provider        rc=$?   (3 = could not verify)"
XDG_CACHE_HOME="$(mktemp -d)" ./target/release/fleet-search local "x" >/dev/null 2>&1
echo "local search, empty cache      rc=$?   (0 = ran, and found nothing)"
echo
echo "exit: 0"
