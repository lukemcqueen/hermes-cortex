#!/usr/bin/env python3
"""Daily watchdog: notify when upstream hermes-agent fixes the _stdio_children_dead() inversion.

Fleet incident 2026-08-25: upstream commit 2f33833de (Aug 24) introduced an
inverted return in MCPServerTask._stdio_children_dead() (tools/mcp_tool.py):
it returned True when a tracked stdio child was ALIVE, so the gateway
fast-failed every healthy stdio MCP tool call with
'TimeoutError: MCP stdio subprocess for <server> has exited' in 0.0s.
Follow-up 786f37071 preserved the inversion; still on origin/main as of
64a6f42cb. Fleet pinned to v2026.8.19 and paused agent-hermes-update crons
until upstream fixes it.

This watchdog polls origin/main's mcp_tool.py daily:
  - bug still present -> silent (exit 0, no output)
  - fix detected      -> prints ONE notification (marker file dedupes)
  - fetch failure     -> error alert (exit 1) so a broken check can't go silent

Watchdog pattern (cron-format-standard): empty stdout = silent tick.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.request

DEFAULT_URL = "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/tools/mcp_tool.py"
MARKER = os.path.expanduser("~/.hermes/state/upstream-hermes-fix-notified")

# The buggy alive-branch marker: the inverted return that made the caller
# believe a healthy subprocess had exited. Any sane fix removes or rewrites
# this exact line (or deletes the whole function).
BUGGY_MARKER = "return True  # alive"

NOTIFY_TEXT = (
    "\U0001f7e2 UPSTREAM FIX DETECTED: hermes-agent _stdio_children_dead() "
    "inversion is fixed on origin/main.\n"
    "Fleet action:\n"
    "  1. Run `hermes update` on all hosts (moses, esther, joseph, gisu, kustos, titus)\n"
    "  2. Resume the paused agent-hermes-update crons (`hermes cron resume <job_id>`)\n"
    "  3. Verify: grep -c '_stdio_children_dead' tools/mcp_tool.py on each host "
    "(0 = clean; or confirm the fixed return logic)\n"
    "  4. Remove the v2026.8.19 pin once all hosts verify clean."
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-cortex-fix-watchdog"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def is_fixed(src: str) -> bool:
    """True when the buggy inverted-return pattern is gone from the file."""
    # Function absent entirely -> fast-fail machinery removed/renamed -> bug gone.
    if "_stdio_children_dead" not in src:
        return True
    m = re.search(r"def _stdio_children_dead[^:]*:\n(.*?)(?=\n    (?:async )?def )", src, re.S)
    if not m:
        # Present but parse failed — be conservative: not fixed.
        return False
    body = m.group(1)
    if BUGGY_MARKER in body:
        return False
    # A real fix keeps an alive-child False path; a stub with no returns is
    # not a fix we should wake the fleet for.
    return "return False" in body


def main(argv: list[str]) -> int:
    url = argv[0] if argv else DEFAULT_URL
    dry_run = url == "--dry-run" or (argv and "--dry-run" in argv)
    if dry_run:
        url = next((a for a in argv if a.startswith("http")), DEFAULT_URL)
    try:
        src = fetch(url)
    except Exception as exc:  # network/HTTP errors — alert, don't guess
        print(f"CHECK FAILED: could not fetch {url}: {exc}", file=sys.stderr)
        return 1
    if not is_fixed(src):
        return 0  # silent — bug still present
    if not dry_run and os.path.exists(MARKER):
        return 0  # already notified once
    print(NOTIFY_TEXT)
    if not dry_run:
        os.makedirs(os.path.dirname(MARKER), exist_ok=True)
        with open(MARKER, "w", encoding="utf-8") as fh:
            fh.write("notified\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
