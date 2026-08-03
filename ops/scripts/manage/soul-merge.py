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
import subprocess
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
        pass  # intentional: file-missing returns empty str, caller handles it
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

        # Match principle headings: ### N. Title (also accept #### for legacy format)
        m = re.match(r'^(#{3,4} (\d+)\.\s+.+)$', line)
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
    When a marker line is missing, the ENTIRE sub-point block is returned —
    the marker line PLUS any wrapped continuation lines that belong to it
    (following non-blank lines that do not start a new bold marker). A
    marker-only return silently dropped continuations (observed 2026-08-03:
    '**Governance fixes fail closed** — never delete or weaken enforcement or'
    propagated without its 'scoring to silence a warning; warn+exit0 is a
    bypass.' continuation line).
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
    i = 0
    n = len(template_subs)
    while i < n:
        line = template_subs[i]
        m = re.search(r'\*\*([^*]+)\*\*', line)
        if m and m.group(1).strip() not in agent_markers:
            # Marker line missing → grab the whole block: marker line plus
            # following non-blank lines until the next marker or the end.
            block = [line]
            i += 1
            while i < n:
                nxt = template_subs[i]
                if nxt.strip() == "":
                    break
                if re.search(r'\*\*([^*]+)\*\*', nxt):
                    break  # next sub-point begins
                block.append(nxt)
                i += 1
            missing.extend(block)
        else:
            i += 1
    return missing


def _title_key(heading: str) -> str:
    """Normalize a principle heading to a number-agnostic title key.

    Local SOULs accumulate agent-specific principles and their numbering
    drifts from the template's (e.g. local P11 'No Bypass Flags' vs template
    P11 'No Buck-Passing'). Matching must be by title, not number.
    """
    return re.sub(r'^#{3,4}\s*\d+\.\s*', '', heading).strip().lower()


def _previous_template_titles() -> set:
    """Titles from the previous committed template version (via git).

    Used to distinguish *stale pre-consolidation template principles* (safe
    to drop) from *genuinely agent-specific principles* (never in any
    template — must be preserved). Returns the title-key set of the template
    at the commit before the one that introduced the current template.
    """
    titles: set = set()
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_DIR), "log", "-2", "--format=%H", "--",
             "docs/templates/SOUL.md"],
            capture_output=True, text=True, timeout=15,
        ).stdout.split()
        if len(out) >= 2:
            prev = subprocess.run(
                ["git", "-C", str(REPO_DIR), "show", f"{out[1]}:docs/templates/SOUL.md"],
                capture_output=True, text=True, timeout=15,
            ).stdout
            for heading in re.findall(r"^#{3,4} \d+\..+$", prev, re.M):
                titles.add(_title_key(heading))
    except Exception:
        pass  # git unavailable → fall back to template-only rebuild
    return titles


def _render_principles(principles: dict, template_principles: dict) -> str:
    """Render the principles section, merging template updates into agent copy.

    Matching is by principle TITLE, not number. Number-only matching injected
    template subpoints into the wrong local principle (observed 2026-07-31:
    template P17 'Never Print Secrets' Pattern line landed in local P17
    'Recommend Improvements'; template P20 'Take Responsibility' bullet landed
    in local P20 'Unattended Destructive Actions'), and re-injected them on
    every cortex-update.

    For each local principle, merge missing sub-points from the template
    principle with the same title. Template principles whose title is absent
    from the agent's copy are injected in template order.
    """
    template_by_title = {_title_key(tp["heading"]): tp for tp in template_principles.values()}
    local_by_title = {_title_key(p["heading"]): p for p in principles.values()}
    output_lines = []
    last_tier = None

    # 1. Render local principles in order, merging same-title template subpoints
    for num in sorted(principles.keys()):
        p = principles[num]
        tp = template_by_title.get(_title_key(p["heading"]))

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

    # 2. Inject template principles whose title is absent from the agent's copy
    for tnum in sorted(template_principles.keys()):
        tp = template_principles[tnum]
        if _title_key(tp["heading"]) in local_by_title:
            continue
        # Stop at the scripture block (### <Book> — ...): the deployed
        # copy's scripture entries track the agent's own reading progress
        # and must not be duplicated or overridden by template seeds.
        # The block is contiguous at the tail of the template's subpoints,
        # so break (not continue) to drop its description lines too.
        subs = []
        for s in tp["subpoints"]:
            if re.match(r'^### [A-Za-z0-9 ]+ —', s.strip()):
                break
            subs.append(s)
        if output_lines and output_lines[-1].strip() != "":
            output_lines.append("")
        output_lines.append(tp["heading"])
        output_lines.append("")
        output_lines.extend(subs)
        output_lines.append("")

    return "\n".join(output_lines)


def _render_consolidated(principles: dict, template_principles: dict, stale_titles: set) -> str:
    """Render the principles section after a template consolidation.

    The template is authoritative: render its principles in template order
    (merging missing template subpoints into same-title local principles).
    Agent principles whose title is in the template are merged; agent
    principles whose title is in NEITHER the template NOR the previous
    template are genuinely agent-specific and preserved; everything else
    (stale pre-consolidation template content) is dropped.
    """
    template_by_title = {_title_key(tp["heading"]): tp for tp in template_principles.values()}
    local_by_title = {_title_key(p["heading"]): p for p in principles.values()}
    output_lines = []
    last_tier = None
    dropped = []

    # 1. Render template principles in template order
    for tnum in sorted(template_principles.keys()):
        tp = template_principles[tnum]
        p = local_by_title.get(_title_key(tp["heading"]))

        tier = tp.get("tier", "")
        if tier and tier != last_tier:
            if tier not in output_lines:
                output_lines.append("")
                output_lines.append(tier)
                output_lines.append("")
            last_tier = tier

        output_lines.append(tp["heading"])
        output_lines.append("")

        rendered_subs = list(tp["subpoints"])
        if p:
            # Merge missing sub-points from the template into local copy
            missing = _find_missing_subpoints(tp["subpoints"], p["subpoints"])
            if missing:
                if rendered_subs and rendered_subs[-1].strip() == "":
                    for ms in missing:
                        rendered_subs.insert(-1, ms)
                else:
                    rendered_subs.extend(missing)
                    rendered_subs.append("")

        for line in rendered_subs:
            if line == "---" and output_lines and output_lines[-1] == "---":
                continue
            output_lines.append(line)

    # 2. Keep genuinely agent-specific principles (never in any template)
    for num in sorted(principles.keys()):
        p = principles[num]
        title_key = _title_key(p["heading"])
        if title_key in template_by_title:
            continue
        if title_key in stale_titles:
            dropped.append(p["heading"])
            continue
        # Genuinely agent-specific — preserve
        tier = p.get("tier", "")
        if tier and tier != last_tier:
            if tier not in output_lines:
                output_lines.append("")
                output_lines.append(tier)
                output_lines.append("")
            last_tier = tier
        output_lines.append(p["heading"])
        output_lines.append("")
        for line in p["subpoints"]:
            if line == "---" and output_lines and output_lines[-1] == "---":
                continue
            output_lines.append(line)
        output_lines.append("")

    if dropped:
        print(f"  🗑️  Dropped {len(dropped)} stale pre-consolidation principle(s):")
        for h in dropped:
            print(f"       • {h}")

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
        print("expected — silently handled", file=sys.stderr)
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

    # Find new principles and missing sub-points — matched by TITLE, not
    # number: local SOUL numbering drifts from the template (agents add their
    # own principles), and number-only matching mis-attributed template
    # subpoints to the wrong local principle.
    local_by_title = {_title_key(p["heading"]): p for p in agent_p.values()}
    new_principles = []
    new_subpoints = []

    for num in sorted(template_p.keys()):
        tp = template_p[num]
        ap = local_by_title.get(_title_key(tp["heading"]))
        if ap is None:
            # Entire new principle (title absent from the agent's copy)
            new_principles.append(tp["heading"])
        else:
            # Check for new sub-points in the same-title principle
            missing = _find_missing_subpoints(tp["subpoints"], ap["subpoints"])
            if missing:
                new_subpoints.append((num, tp["heading"], missing))

    # ── Consolidation detection ─────────────────────────────────────────
    # If the template has FEWER principles than the deployed copy, the
    # template was consolidated (34→12, 2026-08-02). Pre-fix behaviour
    # APPENDED template principles on top of stale pre-consolidation ones,
    # stacking 34 old + 12 new = 46 principles and blowing the size budget
    # (Joseph report 2026-08-03: deployed SOUL ballooned to 26,957 B, doctor
    # FAIL). On consolidation, REBUILD the section from the template as
    # authoritative, dropping stale template-origin principles while keeping
    # genuinely agent-specific ones (title never in any template version).
    #
    # Gate on stale titles actually being PRESENT in the agent copy: an
    # agent with extra custom principles (13 > 12) but no old-template
    # leftovers must NOT re-trigger consolidation on every run (idempotency).
    # "Stale" = title in the PREVIOUS template but NOT in the current one —
    # titles that survived the consolidation (Loop Governance, Be Concise…)
    # exist in both and must not count as stale.
    stale_titles = _previous_template_titles().difference(
        {_title_key(tp["heading"]) for tp in template_p.values()}
    )
    agent_title_keys = {_title_key(p["heading"]) for p in agent_p.values()}
    has_stale = bool(stale_titles.intersection(agent_title_keys))
    # <= (not <): the 2026-08-03 restructure REPLACED all 12 titles at an
    # equal count (12 old → 12 new). A strict < saw 12 < 12 == False and
    # appended the new titles onto the stale ones — 24 stacked principles,
    # 23K balloon, doctor FAIL. <= fires on both count reductions (34→12)
    # and equal-count title replacements (12→12); the has_stale gate keeps
    # custom-extra agents (no stale leftovers) from re-triggering.
    consolidation = has_stale and len(template_p) <= len(agent_p)

    changes = bool(new_principles) or bool(new_subpoints) or consolidation

    if not changes:
        print(f"✅ SOUL.md is up to date with template. No merge needed.")
        return 0

    # Report what would change
    if new_principles:
        for h in new_principles:
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

    if consolidation:
        # Rebuild the section from the template as authoritative. Render
        # template principles in template order; keep only agent principles
        # whose title is NOT in the template AND NOT in the previous template
        # (genuinely agent-specific — preserved); drop stale pre-consolidation
        # template-origin principles.
        merged_principles = _render_consolidated(
            agent_p, template_p, stale_titles=stale_titles
        )
    else:
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
