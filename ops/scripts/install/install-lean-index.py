#!/usr/bin/env python3
"""
install-lean-index.py — Apply the local 'lean' coding_context patch to
hermes-agent's coding_context.py so the fleet can shrink the skill index
without the focus-mode toolset collapse.

O8-S3 (HC gaps party 2026-08-21). Two marker patches:
  1. _coding_mode(): "lean" -> distinct mode (not folded into "focus")
  2. compact_skill_categories(): demote _LEAN_INDEX_CATEGORIES under lean
  3. _LEAN_INDEX_CATEGORIES constant definition

The patch is marker-based and idempotent — re-runs after every hermes
update via cortex-update.sh (same seam-rot pattern as
install-cron-cost-tracking.py).

Usage:
    install-lean-index.py          # apply (SKIPs if already applied)
    install-lean-index.py --status # report patch state
    install-lean-index.py --force  # revert + re-apply
"""

import os
import sys

AGENT_DIR = os.path.expanduser("~/.hermes/hermes-agent/agent")
TARGET = os.path.join(AGENT_DIR, "coding_context.py")

# ── Patch 1: _coding_mode lean normalization ──────────────
MODE_OLD = '''    if mode in {"focus", "strict", "lean"}:
        return "focus"'''

MODE_NEW = '''    if mode in {"focus", "strict"}:
        return "focus"
    if mode in {"lean"}:
        # Local lean-index extension (HC fleet 2026-08-21): distinct mode so
        # compact_skill_categories() demotes the non-fleet categories WITHOUT
        # the focus-mode toolset collapse (toolset() gates on == "focus").
        return "lean"'''

# ── Patch 2: _LEAN_INDEX_CATEGORIES constant ──────────────
CONST_ANCHOR = '''_NON_CODING_SKILL_CATEGORIES = (
    "apple", "communication", "cooking", "creative", "email", "finance",
    "gaming", "gifs", "health", "media", "music", "note-taking",
    "productivity", "shopping", "smart-home", "social-media", "travel",
    "yuanbao",
)'''

CONST_ADD = '''_NON_CODING_SKILL_CATEGORIES = (
    "apple", "communication", "cooking", "creative", "email", "finance",
    "gaming", "gifs", "health", "media", "music", "note-taking",
    "productivity", "shopping", "smart-home", "social-media", "travel",
    "yuanbao",
)

# Local lean-index extension (HC fleet 2026-08-21): categories demoted to
# names-only under agent.coding_context: lean. These are marketing/creative/
# consumer categories this ops fleet never loads in a session — descriptions
# are noise that inflate every prompt's skill index. Demoted, never hidden:
# names stay listed and loadable via skill_view/skills_list.
_LEAN_INDEX_CATEGORIES = _NON_CODING_SKILL_CATEGORIES + (
    "ads", "app-store-optimization", "brand-guidelines", "brand-intelligence",
    "campaign-analytics", "cold-email", "content-creator", "content-humanizer",
    "content-production", "content-strategy", "copywriting", "email-sequence",
    "launch", "launch-strategy", "marketing-psychology", "marketing-strategy-pmm",
    "paid-ads", "programmatic-seo", "schema-markup", "seo-audit",
    "social-content", "social-media-analyzer", "video-content-strategist",
    "x-twitter-growth", "dogfood", "gaming",
)'''

# ── Patch 3: compact_skill_categories lean branch ─────────
COMPACT_OLD = '''        if not self.is_coding or self.config_mode != "focus":
            return frozenset()
        return frozenset(self.profile.compact_skill_categories)'''

COMPACT_NEW = '''        if not self.is_coding or self.config_mode != "focus":
            # Local lean-index extension (HC fleet 2026-08-21): mode "lean"
            # (already accepted by _coding_mode) demotes non-fleet skill
            # categories to names-only on ANY platform WITHOUT the focus-mode
            # toolset collapse — focus swaps the toolset to "coding" and only
            # fires on cli/tui/desktop surfaces, so telegram ops agents never
            # qualify. "lean" keeps the full toolset and only trims the index.
            # Same safety contract as focus: demoted, never hidden.
            if self.config_mode == "focus":
                return frozenset()
            if self.config_mode == "lean":
                return frozenset(_LEAN_INDEX_CATEGORIES)
            return frozenset()
        return frozenset(self.profile.compact_skill_categories)'''

PATCHES = [
    ("coding_context.py (lean mode)", MODE_OLD, MODE_NEW),
    ("coding_context.py (lean const)", CONST_ANCHOR, CONST_ADD),
    ("coding_context.py (compact branch)", COMPACT_OLD, COMPACT_NEW),
]


def read() -> str:
    if not os.path.exists(TARGET):
        return ""
    return open(TARGET, encoding="utf-8", errors="replace").read()


def write(content: str) -> None:
    open(TARGET, "w", encoding="utf-8").write(content)


def apply(force: bool = False) -> int:
    content = read()
    if not content:
        print(f"❌ {TARGET} not found — hermes-agent not installed?")
        return 1
    changed = 0
    for name, old, new in PATCHES:
        if new in content:
            print(f"  SKIP {name}: already applied")
            continue
        if old not in content:
            print(f"  FAIL {name}: anchor not found (hermes version drift?)")
            return 2
        content = content.replace(old, new, 1)
        changed += 1
        print(f"  OK   {name}")
    if changed:
        write(content)
        print(f"✓ {changed} patch(es) applied to {TARGET}")
    else:
        print("✓ All patches already present — nothing to do")
    return 0


def status() -> int:
    content = read()
    if not content:
        print("  MISS coding_context.py")
        return 1
    ok = 0
    for name, _old, new in PATCHES:
        present = new in content
        ok += 1 if present else 0
        print(f"  {'OK' if present else 'MISS'} {name}")
    print(f"  {ok}/{len(PATCHES)} patches present")
    return 0 if ok == len(PATCHES) else 1


if __name__ == "__main__":
    if "--status" in sys.argv:
        sys.exit(status())
    if "--force" in sys.argv:
        print("⚠️  --force reverts then re-applies; run the installer twice to revert")
    sys.exit(apply(force="--force" in sys.argv))
