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
echo "== the committed test inventory still matches the source =="
# A name list that has drifted from the tests is worse than no list: it reads as authoritative.
# Regenerating and diffing means adding or renaming a test fails HERE until the inventory is
# updated, so the file cannot quietly describe a suite that no longer exists.
inventory_tmp="$(mktemp)"
cargo test -- --list 2>/dev/null | grep -E ": test$" > "$inventory_tmp"
if diff -q test-inventory.txt "$inventory_tmp" >/dev/null 2>&1; then
  echo "  matches: $(wc -l < test-inventory.txt | tr -d ' ') tests"
else
  echo "  DRIFT — test-inventory.txt does not match the source:" >&2
  diff test-inventory.txt "$inventory_tmp" | sed 's/^/    /' >&2
  echo "  Fix: cargo test -- --list | grep -E ': test\$' > test-inventory.txt" >&2
  rm -f "$inventory_tmp"
  exit 1
fi
rm -f "$inventory_tmp"

echo
echo "exit: 0"
