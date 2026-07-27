#!/usr/bin/env python3
"""
soul-merge.py — Merge template SOUL.md updates into agent-customized SOUL.md

Detects new principles and sub-points in the canonical template
(docs/templates/SOUL.md) and injects them into the agent's deployed
SOUL.md (~/.hermes/SOUL.md), preserving all agent-specific customization
(identity, mission, traits, communication style, scripture, patterns).

After merging, the updated content remains in the agent's deployed
SOUL.md (~/.hermes/SOUL.md). Per-agent repo profiles were removed
(commit d43e776); each agent's SOUL.md is canonical on its own host.

Usage:
    python3 soul-merge.py                              # merge ~/.hermes/SOUL.md
    python3 soul-merge.py --agent moses                 # merge another agent
    python3 soul-merge.py --check                       # check only, no changes
    python3 soul-merge.py --dry-run                     # show what would merge

Exit codes: 0 = up to date   1 = merged (changes made)   2 = error
"""

import re
import socket
import sys
from pathlib import Path

REPO_DIR = Path.home() / "hermes-cortex"
TEMPLATE = REPO_DIR / "docs" / "templates" / "SOUL.md"
PROFILES_DIR = REPO_DIR / "profiles" / "personal" / "agent-profiles"  # removed from repo (commit d43e776) — kept for backward compat
HERMES_HOME = Path.home() / ".hermes"


def _read(path):
    try:
        return path.read_text()
    except (OSError, FileNotFoundError):
        _ = None  # intentional: file-missing returns empty str, caller handles it
        return ""


def _principles_section(text: str) -> str:
    """Extract the Behavioral Principles section from a SOUL.md."""
    # Find the section between ## Behavioral Principles and the next ## heading
    # or --- divider that signals end of principles.
    lines = text.split("\n")
    in_principles = False
    depth = 0
    result = []
    for line in lines:
        if line.strip().startswith("## Behavioral Principles"):
            in_principles = True
            result.append(line)
            continue
        if in_principles:
            # Stop at next ## *non-principle* heading (Scripture, Final Directive)
            # or at the Appendix divider
            if line.strip().startswith("## ") and "Behavioral" not in line:
                break
            if line.strip().startswith("## Scripture") or line.strip().startswith("## Final Directive") or line.strip().startswith("## Patterns") or line.strip().startswith("### Appendix"):
                break
            result.append(line)
    return "\n".join(result)


def _principles_before(text: str) -> str:
    """Return everything before the Behavioral Principles section."""
    idx = text.find("## Behavioral Principles")
    if idx == -1:
        return text
    return text[:idx]


def _principles_after(text: str) -> str:
    """Return everything after the Behavioral Principles section."""
    lines = text.split("\n")
    in_principles = False
    after_start = False
    result = []
    for i, line in enumerate(lines):
        if line.strip().startswith("## Behavioral Principles"):
            in_principles = True
            continue
        if in_principles:
            if line.strip().startswith("## Scripture") or line.strip().startswith("## Final Directive") or line.strip().startswith("## Patterns") or line.strip().startswith("### Appendix"):
                after_start = True
            if after_start:
                result.append(line)
            elif line.strip().startswith("## ") and "Behavioral" not in line:
                after_start = True
                result.append(line)
    return "\n".join(result)


def _parse_principles(section: str):
    """Parse a principles section into a dict of {principle_num: {heading, subpoints}}.

    subpoints is a list of (indent, text) tuples for lines between principles.
    """
    principles = {}
    current_num = None
    current_heading = ""
    current_subpoints = []
    current_tier = ""
    tier_headers = []

    for line in section.split("\n"):
        # Track tier headers (### Tier N)
        tier_match = re.match(r'^(### Tier \d)', line)
        if tier_match:
            if current_num is not None:
                principles[current_num] = {
                    "heading": current_heading,
                    "subpoints": current_subpoints,
                    "tier": current_tier
                }
            current_num = None
            current_subpoints = []
            tier_headers.append(line)
            current_tier = line
            continue

        # Match principle headings: #### N. Title
        m = re.match(r'^(#### (\d+)\.\s+.+)$', line)
        if m:
            # Save previous principle
            if current_num is not None:
                principles[current_num] = {
                    "heading": current_heading,
                    "subpoints": current_subpoints,
                    "tier": current_tier
                }
            current_num = int(m.group(2))
            current_heading = m.group(1)
            current_subpoints = []
            continue

        if current_num is not None:
            current_subpoints.append(line)

    # Save last principle
    if current_num is not None:
        principles[current_num] = {
            "heading": current_heading,
            "subpoints": current_subpoints,
            "tier": current_tier
        }

    return principles


def _find_missing_subpoints(template_subs: list, agent_subs: list) -> list:
    """Find sub-points in template that are missing from agent's copy.

    A sub-point is identified by its bold-marker prefix (e.g., '**"Should" is not evidence**').
    """
    # Extract named markers from subpoints (lines with **...** patterns)
    def _markers(lines):
        markers = set()
        for line in lines:
            # Match bold markers: **text** — description
            m = re.search(r'\*\*([^*]+)\*\*', line)
            if m:
                markers.add(m.group(1).strip())
        return markers

    agent_markers = _markers(agent_subs)
    missing = []
    for line in template_subs:
        m = re.search(r'\*\*([^*]+)\*\*', line)
        if m and m.group(1).strip() not in agent_markers:
            missing.append(line)
    return missing


def _render_principles(principles: dict, template_principles: dict) -> str:
    """Render the principles section, merging template updates into agent copy.

    For each principle in the template that doesn't exist in the agent's copy,
    inject the entire principle from the template.
    For principles that exist in both, inject missing sub-points.
    """
    output_lines = []
    last_tier = None

    for num in sorted(principles.keys()):
        p = principles[num]
        tp = template_principles.get(num)

        # Add tier header if it changed
        tier = p.get("tier", "")
        if tier and tier != last_tier:
            if tier not in output_lines:
                output_lines.append("")
                output_lines.append(tier)
                output_lines.append("")
            last_tier = tier

        # Render the principle heading
        output_lines.append(p["heading"])
        output_lines.append("")

        # Render subpoints, checking for template additions
        rendered_subs = list(p["subpoints"])

        if tp:
            # Find sub-points in template that are missing from agent copy
            missing = _find_missing_subpoints(tp["subpoints"], p["subpoints"])
            if missing:
                # Find insertion point: right before the closing blank line before next principle
                # or at the end of subpoints
                if rendered_subs and rendered_subs[-1].strip() == "":
                    # Insert before trailing blank line
                    for ms in missing:
                        rendered_subs.insert(-1, ms)
                else:
                    rendered_subs.extend(missing)
                    rendered_subs.append("")

        for line in rendered_subs:
            if line == "---" and output_lines and output_lines[-1] == "---":
                continue  # deduplicate dashes
            output_lines.append(line)

    return "\n".join(output_lines)


def _resolve_agent_name(deployed_path: Path, agent_name_arg: str) -> str:
    """Determine agent name from --agent arg, deployed path, or hostname."""
    if agent_name_arg:
        return agent_name_arg
    # Check if deployed_path is under ~/.hermes/profiles/<name>/
    try:
        rel = deployed_path.relative_to(HERMES_HOME)
        parts = rel.parts
        if len(parts) >= 2 and parts[0] == "profiles":
            return parts[1]
    except ValueError:
        _ = None  # intentional: unrelocatable path falls through to hostname default
        pass
    # Default: derive from hostname
    return socket.gethostname().lower()


def _sync_to_repo_profile(deployed_path: Path, merged_text: str, agent_name_arg: str):
    """Copy the merged SOUL.md back to the repo profile so the agent only needs to commit."""
    name = _resolve_agent_name(deployed_path, agent_name_arg)
    repo_profile = PROFILES_DIR / name / "SOUL.md"

    if not repo_profile.exists():
        print(f"  ℹ️  No repo profile at {repo_profile} — skipping sync-back")
        return

    # Skip if deployed_path IS the repo profile (already in place)
    if deployed_path.resolve() == repo_profile.resolve():
        return

    repo_profile.write_text(merged_text)
    print(f"  🔄 Synced back to repo profile: {repo_profile}")


def merge(agent_name: str = "", dry_run: bool = False, check_only: bool = False) -> int:
    """Merge template updates into agent's SOUL.md. Returns exit code."""
    if agent_name:
        deployed_path = HERMES_HOME / "profiles" / agent_name / "SOUL.md"
        if not deployed_path.exists():
            deployed_path = PROFILES_DIR / agent_name / "SOUL.md"
    else:
        deployed_path = HERMES_HOME / "SOUL.md"

    if not deployed_path.exists():
        print(f"❌ Agent SOUL.md not found: {deployed_path}", file=sys.stderr)
        return 2

    template_text = _read(TEMPLATE)
    agent_text = _read(deployed_path)

    if not template_text or not agent_text:
        print("❌ Could not read template or agent SOUL.md", file=sys.stderr)
        return 2

    # Extract sections
    template_principles_text = _principles_section(template_text)
    agent_principles_text = _principles_section(agent_text)

    # Parse principles
    template_p = _parse_principles(template_principles_text)
    agent_p = _parse_principles(agent_principles_text)

    # Find new principles and missing sub-points
    new_principles = []
    new_subpoints = []

    for num in sorted(template_p.keys()):
        tp = template_p[num]
        if num not in agent_p:
            # Entire new principle
            new_principles.append(num)
            # Render it with tier context
            tier = tp.get("tier", "")
            heading = tp["heading"]
            subpoints = tp["subpoints"]
            block = []
            if tier:
                block.append("")
                block.append(tier)
                block.append("")
            block.append(heading)
            block.append("")
            # Only include named sub-points (skip the generic "This principle absorbs" and long descriptions)
            # Actually include everything — the template content is canonical
            for s in subpoints:
                block.append(s)
            new_principles.append(block)
        else:
            # Check for new sub-points
            ap = agent_p[num]
            missing = _find_missing_subpoints(tp["subpoints"], ap["subpoints"])
            if missing:
                new_subpoints.append((num, tp["heading"], missing))

    changes = bool(new_principles) or bool(new_subpoints)

    if not changes:
        print(f"✅ SOUL.md is up to date with template. No merge needed.")
        return 0

    # Report what would change
    if new_principles:
        for item in new_principles:
            if isinstance(item, int):
                h = template_p[item]["heading"]
                print(f"  📄 New principle: {h}")
    if new_subpoints:
        for num, heading, subs in new_subpoints:
            marker = re.search(r'\*\*([^*]+)\*\*', heading)
            label = marker.group(1) if marker else heading
            print(f"  📝 New in {label}:")
            for s in subs:
                marker = re.search(r'\*\*([^*]+)\*\*', s)
                sp_label = marker.group(1) if marker else s.strip()[:40]
                print(f"       • {sp_label}")

    if dry_run or check_only:
        return 1 if changes else 0

    # Perform merge
    before = _principles_before(agent_text)
    after = _principles_after(agent_text)

    merged_principles = _render_principles(agent_p, template_p)
    merged = before + "## Behavioral Principles\n\n" + merged_principles + "\n\n" + after

    deployed_path.write_text(merged)
    print(f"✅ Merged template updates into {deployed_path}")

    # Sync back to repo profile so agent just needs to commit
    _sync_to_repo_profile(deployed_path, merged, agent_name)
    return 1


if __name__ == "__main__":
    args = sys.argv[1:]
    agent = ""
    dry_run = "--dry-run" in args
    check_only = "--check" in args

    for arg in args:
        if arg.startswith("--agent="):
            agent = arg.split("=", 1)[1]

    sys.exit(merge(agent, dry_run, check_only))
