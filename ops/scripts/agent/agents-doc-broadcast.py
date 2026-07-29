#!/usr/bin/env python3
"""
agents-doc-broadcast.py — Send inbox message to all agents that AGENTS.md or SOUL.md changed.

Usage:
  python3 agents-doc-broadcast.py AGENTS.md "Section X was updated: new inbox decision framework"
  python3 agents-doc-broadcast.py --dry-run SOUL.md "Added audit trail principle"

Sends to: all agents via inbox, with CC to Luke.
"""

import argparse
import os
import sys
import json


def main():
    parser = argparse.ArgumentParser(description="Broadcast AGENTS.md/SOUL.md changes to all agents")
    parser.add_argument("doc_type", choices=["AGENTS.md", "SOUL.md"], help="Which document changed")
    parser.add_argument("change_summary", help="What changed (one line)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent without sending")
    args = parser.parse_args()

    targets = ["gisu", "joseph", "kustos", "titus", "esther"]

    if args.dry_run:
        print(f"🔍 DRY RUN — Would broadcast to {len(targets)} agents:")
        for t in targets:
            print(f"  → {t}: {args.doc_type} changed — {args.change_summary}")
        print("  → CC: luke")
        sys.exit(0)

    # Attempt inbox send via MCP
    try:
        # We can't directly call MCP tools from a standalone script,
        # but we can produce the output for the cron to parse
        print(json.dumps({
            "action": "broadcast",
            "doc_type": args.doc_type,
            "change_summary": args.change_summary,
            "targets": targets,
            "note": "Run via agent inbox — use mcp_agent_inbox_inbox_send for each target"
        }))
        print()
        print("---INBOX-BROADCAST-MARKER---")
        print(f"Subject: 📋 {args.doc_type} updated — review and integrate")
        print(f"Body: {args.doc_type} has been updated by Moses.")
        print(f"")
        print(f"**What changed:** {args.change_summary}")
        print(f"")
        print(f"**Action required:**")
        print(f"1. Read the updated {args.doc_type}")
        print(f"2. Check your own SOUL.md for gaps against the new template")
        print(f"3. The orch-skill-lifecycle cron (04:00 daily) will auto-fill gaps (Channel C)")
        print(f"")
        print(f"**Location:** `~/hermes-cortex/AGENTS.md` or `~/.hermes/SOUL.md`")
        print(f"**Reference template:** `~/hermes-cortex/docs/templates/SOUL.md`")
        print("---END-MARKER---")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Broadcast failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()