#!/usr/bin/env python3
"""
template-diff-check.py — Compare local agent files against repo templates.

After every git pull, this script checks whether the agent's personal
files (SOUL.md, AGENTS.md) are structurally current with the repo templates.
It detects:
- Missing sections (template has a section the local copy lacks)
- Stale content markers (e.g. "skip=self-destruct" vs "MCP-enforced")
- Deprecated patterns that indicate an agent hasn't updated

Exit: 0 = all current, 1 = one or more files are stale
"""

import os
import re
import sys

HERMES_CORTEX = os.path.expanduser("~/hermes-cortex")
HERMES_DIR = os.path.expanduser("~/.hermes")

# ── Section extraction ───────────────────────────────────────

def extract_sections(filepath):
    """Return dict of {section_name: section_body} from a markdown file.
    Sections start with '## ' (level-2 headers).
    """
    sections = {}
    current_section = "__header__"
    current_lines = []

    try:
        with open(filepath) as f:
            for line in f:
                if line.startswith("## "):
                    if current_lines:
                        sections[current_section] = "".join(current_lines)
                    current_section = line.lstrip("# ").strip()
                    current_lines = [line]
                else:
                    current_lines.append(line)

        if current_lines:
            sections[current_section] = "".join(current_lines)
    except FileNotFoundError:
        _ = None  # expected — silently handled
    return sections


# ── Stale marker definitions ─────────────────────────────────
#
# Each entry: section_name -> list of (marker_string, description)
# The check PASSES if ANY marker in the list is found in the section.
# This lets us update markers as the template evolves without
# false-positives from agents on different versions.

STALE_MARKERS = {
    "Loop Governance": [
        # Version 2 markers (MCP-enforced, current as of 2026-07-03)
        ("MCP-enforced", "pre-commit hook enforcement → MCP server enforcement"),
        ("loop-gov-mcp.py", "MCP-level enforcement"),
        ("begin_change", "governance lock workflow"),
        # Version 1 markers (pre-commit-enforced, OLD — match to warn)
    ],
}

# Deprecated patterns — if ANY of these appear, flag as stale
# (section_name -> list of deprecated substrings)
DEPRECATED_PATTERNS = {
    "Loop Governance": [
        "skip = self-destruct",
        "pre-commit hook is a safety net",
        "Three strikes → propose",
        "Strike 3 → propose",
        "(Strike 3 → propose",
    ],
}


def check_file(template_path, local_path, label):
    """Compare a local file against its template. Returns list of issue strings."""
    issues = []

    if not os.path.exists(template_path):
        return []  # no template to compare against

    if not os.path.exists(local_path):
        issues.append(f"  {label}: File not found at {local_path}")
        return issues

    template_sections = extract_sections(template_path)
    local_sections = extract_sections(local_path)

    # 1. Check for missing sections
    skip_sections = {"__header__", "Scripture Insights", "Final Directive"}
    for section in template_sections:
        if section in skip_sections:
            continue
        if section not in local_sections:
            clean_label = label.replace(" Template", "")
            issues.append(f"  [{clean_label}] Missing section: '{section}'")

    # 2. Check for stale content markers
    for section, markers in STALE_MARKERS.items():
        body = local_sections.get(section, "")
        if not body:
            continue  # section doesn't exist — already caught above
        found_any_current = any(
            marker in body for marker, _ in markers
        )
        if not found_any_current:
            suggestion = markers[0][1] if markers else "check template"
            issues.append(
                f"  [{section}] Content is from an older version — expected: {suggestion}"
            )

    # 3. Check for deprecated patterns
    for section, patterns in DEPRECATED_PATTERNS.items():
        body = local_sections.get(section, "")
        for pattern in patterns:
            if pattern.lower() in body.lower():
                issues.append(
                    f"  [{section}] Deprecated pattern found: '{pattern}'"
                )

    return issues


def main():
    issues = []

    # ── SOUL.md check ───────────────────────────────────────
    issues.extend(check_file(
        os.path.join(HERMES_CORTEX, "docs/templates/SOUL.md"),
        os.path.join(HERMES_DIR, "SOUL.md"),
        "SOUL.md",
    ))

    # ── AGENTS.md check (if repo AGENTS.md exists locally) ──
    # Agents don't have their own AGENTS.md — they read from the
    # repo. Skip this unless the user has a local override.
    agents_local = os.path.join(HERMES_DIR, "AGENTS.md")
    if os.path.exists(agents_local):
        issues.extend(check_file(
            os.path.join(HERMES_CORTEX, "AGENTS.md"),
            agents_local,
            "AGENTS.md",
        ))

    # ── Report ──────────────────────────────────────────────
    if issues:
        print("")
        print("⚠️  Template drift detected — your local files are outdated")
        print("   compared to the hermes-cortex templates.")
        print("")
        for issue in issues:
            print(issue)
        print("")
        print("   To fix:")
        print("   ── Update ~/.hermes/SOUL.md with template changes:")
        print("      diff ~/.hermes/SOUL.md ~/hermes-cortex/docs/templates/SOUL.md")
        print("")
        print("   ── Or view the template directly:")
        print("      cat ~/hermes-cortex/docs/templates/SOUL.md")
        print("")
        return 1

    print("✓  Local files are current with templates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
