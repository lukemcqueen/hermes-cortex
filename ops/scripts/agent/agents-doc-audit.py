#!/usr/bin/env python3
"""
agents-doc-audit.py — Weekly audit of AGENTS.md + SOUL.md files across projects.

Checks each configured SOUL.md for mandatory sections and reports gaps.
Designed to run as a no_agent cron or as an LLM-driven cron with richer reporting.

Usage:
  python3 agents-doc-audit.py                        # default config
  python3 agents-doc-audit.py --config path/to.yaml   # custom config
  python3 agents-doc-audit.py --json                   # machine-readable output
  python3 agents-doc-audit.py --send-report            # deliver via agent inbox
  python3 agents-doc-audit.py --repo .                 # pre-commit hook check
  python3 agents-doc-audit.py --repo . --prune         # dry-run pruning analysis
  python3 agents-doc-audit.py --repo . --prune --apply # execute pruning moves
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Default configuration ──────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "soul_files": [
        {
            "path": "~/.hermes/SOUL.md",
            "agent": "Moses",
            "mandatory_sections": [
                "Identity",
                "Core Mission",
                "Behavioral Principles",
                "Loop governance",
                "Inbox Message Decision Framework",
                "Inbox Audit Trail",
            ],
        },
    ],
    "agents_files": [
        {
            "path": "~/hermes-cortex/AGENTS.md",
            "repo": "hermes-cortex",
            "mandatory_sections": [
                "Agent Execution Contract",
                "Loop Governance",
                "Inbox Message Decision Framework",
                "Doc Freshness",
                "Agent Cron Management",
                "Governance lock",
                "Rule #10: Score Every Change",
                "Real execution, no simulation",
            ],
        },
    ],
    # Pre-commit hook checks these sections when --repo is passed
    "hook_sections": [
        "Agent Execution Contract",
        "Rule #10: Score Every Change",
        "Real execution, no simulation",
        "Pre-commit / pre-push hooks",
    ],
    # Protected sections — never flagged for pruning
    "protected_sections": [
        "What This Repo Does",
        "Key Directories",
        "Architecture Principles",
        "Agent Execution Contract",
        "Loop Governance",
        "Mandatory Agent Workflow",
        "Inbox Message Decision Framework",
        "Doc Freshness",
        "Agent Cron Management",
        "Common Tasks",
        "Reference Docs",
        "Rules",
    ],
}

# ── Pruning rules ──────────────────────────────────────────────────────────
# Each rule: (match_fn, description, suggested_target, priority)
# Higher priority = stronger recommendation to move


def _heading_text(line):
    """Extract clean heading text from a markdown heading line."""
    return re.sub(r"^#+\s+", "", line).strip()


def _count_lines(section_lines):
    """Count non-empty lines in a section."""
    return sum(1 for l in section_lines if l.strip())


def _has_ip_address(text):
    """Check if text contains IP addresses."""
    return bool(re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text))


def _has_url(text):
    """Check if text contains URLs."""
    return bool(re.search(r"https?://[^\s\)]+", text))


def _has_curl_command(text):
    """Check if text contains shell commands."""
    return bool(re.search(r"(?:```\s*(?:bash|sh|shell|zsh)\s*\n|^\$ )", text, re.MULTILINE))


def _has_port_number(text):
    """Check if text contains port numbers."""
    return bool(re.search(r"(?::|\bport\s+)[12]?\d{1,4}\b", text, re.IGNORECASE))


def _is_luke_specific(heading, text):
    """Check if a section is specific to Luke's deployment."""
    return "⚡" in heading or bool(re.search(r"Luke'?s\s+(deployment|setup|multi-agent)", text, re.IGNORECASE))


def _is_setup_or_config(heading, text):
    """Check if section is setup/install/config documentation."""
    setup_keywords = r"(?:setup|install|deployment|configuration|checklist|steps? to|how to set up)"
    return bool(re.search(setup_keywords, heading, re.IGNORECASE))


def _has_file_path(text):
    """Check if text contains file paths."""
    return bool(re.search(r"(?:~|/[\w\-./]+)\.[\w]{1,5}\b", text))


def _code_block_ratio(text):
    """Calculate what fraction of section lines are inside fenced code blocks."""
    lines = text.split("\n")
    if not lines:
        return 0.0
    in_code = False
    code_lines = 0
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
        elif in_code:
            code_lines += 1
    return code_lines / len(lines)


def _has_code_block(text):
    """Check if text contains any fenced code block."""
    return bool(re.search(r"^```", text, re.MULTILINE))


def _is_reference_table(text):
    """Check if section is primarily a large reference table.

    Flags sections where markdown table rows make up >30% of lines
    AND there are at least 5 table body rows.
    """
    lines = text.split("\n")
    if len(lines) < 8:
        return False
    table_rows = sum(1 for l in lines if l.strip().startswith("|"))
    body_rows = table_rows - 2 if table_rows >= 3 else 0  # subtract header + separator
    return body_rows >= 5 and table_rows / len(lines) > 0.3


def _has_deprecated_marker(text):
    """Check for deprecated/legacy/superseded markers in section content.

    Uses specific deprecation vocabulary — avoids ambiguous phrases like
    'moved to' which appear in healthy content relocation notes.
    """
    return bool(re.search(
        r"(?:deprecated|legacy|formerly known|no longer needed|"
        r"superseded|replaced by|no longer used|removed in|stale|obsolete|"
        r"moved to (?:archive|legacy|reference))",
        text, re.IGNORECASE,
    ))


def _has_howto_narrative(text):
    """Check for step-by-step instructions (numbered steps + code blocks)."""
    has_steps = bool(re.search(r"(?:^|\n)\s*\d+\.\s+\w+", text))
    has_code = bool(re.search(r"^```", text, re.MULTILINE))
    return has_steps and has_code


def _is_config_heavy(text):
    """Check if section has long config blocks (YAML/TOML/ini/json)."""
    config_fences = re.findall(
        r"```(?:yaml|toml|ini|json|cfg|conf)\s*\n(.*?)```",
        text, re.DOTALL | re.IGNORECASE,
    )
    if not config_fences:
        return False
    total_config_lines = sum(len(fence.split("\n")) for fence in config_fences)
    return total_config_lines > 10


# Sections to always protect from pruning
ALWAYS_PROTECTED = {
    "What This Repo Does",
    "Key Directories",
    "Architecture Principles",
    "Agent Execution Contract",
    "Rules",
    "Common Tasks",
}

# Merge candidates — sections with overlapping content
MERGE_CANDIDATES = [
    (r"(?i)loop\s*governance", "Loop Governance"),
    (r"(?i)inbox\s*(message)?\s*decision", "Inbox Message Decision Framework"),
    (r"(?i)cron\s*(job|management|architecture)", "Agent Cron Management"),
]


def parse_sections(content):
    """Parse markdown content into a list of (heading, heading_level, lines) tuples."""
    sections = []
    lines = content.split("\n")
    current_heading = "Preamble"
    current_level = 0
    current_lines = []

    for line in lines:
        heading_match = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading_match:
            # Save previous section
            if current_lines or current_heading:
                sections.append((current_heading, current_level, current_lines))
            current_level = len(heading_match.group(1))
            current_heading = heading_match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Save last section
    sections.append((current_heading, current_level, current_lines))
    return sections


def is_protected(heading, protected_list):
    """Check if a section heading matches a protected section."""
    for protected in protected_list:
        if protected.lower() in heading.lower():
            return True
    return False


def is_overlap_with_protected(heading, content, protected_list):
    """Check if section content substantially overlaps a protected section."""
    for protected in protected_list:
        pattern = SECTION_PATTERNS.get(protected)
        if pattern and pattern.search(content):
            return True
    return False


def analyze_section(heading, level, lines, protected_list, config):
    """Analyze a single section for pruning candidacy.

    Collects ALL matching reasons (not just the first) and picks the
    most specific suggested_target by priority.
    """
    text = "\n".join(lines)
    line_count = _count_lines(lines)
    heading_lower = heading.lower()

    # ── Never flag protections ──
    if is_protected(heading, protected_list):
        return None

    # ── Never flag brief structural elements ──
    if line_count < 3:
        return None

    reasons = []
    suggested_target = None

    # ── Collect ALL reasons (independent checks, not elif) ──

    # 1. Luke-specific → fleet docs (highest priority)
    if _is_luke_specific(heading, text):
        reasons.append("⚡ Luke-specific deployment config → belongs in docs/")
        suggested_target = "docs/fleet-reference.md"

    # 2. Deprecated/legacy → needs cleanup
    if _has_deprecated_marker(text):
        reasons.append("Contains deprecated/legacy markers → consider removal or archival")
        if not suggested_target:
            suggested_target = "docs/reference/"

    # 3. Setup/install with concrete addresses → setup docs
    if _is_setup_or_config(heading, text) and (
        _has_ip_address(text) or _has_port_number(text) or _has_url(text)
    ):
        reasons.append("Setup/install documentation with concrete addresses")
        if not suggested_target:
            suggested_target = "docs/setup-reference.md"

    # 4. Config-heavy blocks (YAML/TOML/ini/json > 10 lines)
    if _is_config_heavy(text):
        reasons.append("Long configuration blocks → belongs in docs/")
        if not suggested_target:
            suggested_target = "docs/setup-reference.md"

    # 5. Code-heavy sections (>30% code block lines)
    code_ratio = _code_block_ratio(text)
    if _has_code_block(text) and code_ratio > 0.3 and line_count > 10:
        reasons.append(
            "Code-heavy section ({:.0f}% code, {} lines) → belongs in docs/".format(
                code_ratio * 100, line_count
            )
        )
        if not suggested_target:
            suggested_target = "docs/operations-reference.md"

    # 6. Shell/curl commands (>15 lines, catches non-curl commands too via code_ratio)
    if _has_curl_command(text) and line_count > 15:
        reasons.append("Implementation commands ({} lines) → belongs in docs/".format(line_count))
        if not suggested_target:
            suggested_target = "docs/operations-reference.md"

    # 7. Reference table (primarily tabular data, not policy)
    if _is_reference_table(text):
        reasons.append("Large reference table ({} rows) → belongs in docs/".format(
            sum(1 for l in lines if l.strip().startswith("|"))
        ))
        if not suggested_target:
            suggested_target = "docs/"

    # 8. How-to narrative (numbered steps + code)
    if _has_howto_narrative(text):
        reasons.append("Step-by-step how-to guide → belongs in docs/")
        if not suggested_target:
            suggested_target = "docs/operations-reference.md"

    # 9. Large section fallback (>60 lines, low-specificity signal)
    if line_count > 60 and not suggested_target:
        reasons.append("Large section ({} lines) → candidate for summarization".format(line_count))
        if not suggested_target:
            suggested_target = "docs/reference/"

    # ── Merge candidate check ──
    for pattern, canonical_name in MERGE_CANDIDATES:
        if re.search(pattern, heading) and not is_protected(canonical_name, protected_list):
            if level >= 3:
                reasons.append("Overlaps with '{}' — merge candidate".format(canonical_name))
                if not suggested_target:
                    suggested_target = "inline merge"

    if not reasons:
        return None

    return {
        "heading": heading,
        "level": level,
        "lines": line_count,
        "reasons": reasons,
        "suggested_target": suggested_target,
        "content_preview": text[:200] + ("..." if len(text) > 200 else ""),
    }


def generate_pruning_report(repo_root, content, protected_list, config):
    """Generate a pruning analysis report for AGENTS.md."""
    sections = parse_sections(content)
    candidates = []

    for heading, level, lines in sections:
        result = analyze_section(heading, level, lines, protected_list, config)
        if result:
            candidates.append(result)

    return {
        "repo": repo_root,
        "total_sections": len(sections),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def format_pruning_report(report):
    """Format pruning analysis as human-readable output."""
    lines = []
    lines.append("📋 **AGENTS.md Pruning Analysis**")
    lines.append(f"📂 {report['repo']}")
    lines.append(f"📊 {report['total_sections']} sections, {report['candidate_count']} pruning candidates")
    lines.append("")

    if not report["candidates"]:
        lines.append("✅ No sections flagged for pruning — AGENTS.md is lean.")
        return "\n".join(lines)

    # Group by suggested target
    groups = {}
    for c in report["candidates"]:
        target = c["suggested_target"] or "review"
        groups.setdefault(target, []).append(c)

    for target, candidates in sorted(groups.items()):
        if target == "inline merge":
            lines.append("**🔄 Merge candidates:**")
        elif target == "docs/reference/":
            lines.append("**📚 Summarize → reference docs:**")
        else:
            lines.append(f"**📦 Move to `{target}`:**")
        lines.append("")

        for c in candidates:
            icon = "⚡" if any("Luke" in r for r in c["reasons"]) else "📦"
            lines.append(f"  {icon} **{c['heading']}** ({c['lines']} lines)")
            for r in c["reasons"]:
                lines.append(f"    └ {r}")
            lines.append("")
        lines.append("")

    lines.append("---")
    lines.append("**How to apply:**")
    lines.append("  python3 agents-doc-audit.py --repo <path> --prune --apply")
    lines.append("  (Dry-run by default. --apply moves flagged content to docs/.)")
    lines.append("")

    return "\n".join(lines)


def apply_pruning(repo_root, content, candidates, config):
    """Apply pruning moves: relocate flagged sections to docs/ files."""
    repo = Path(repo_root).resolve()
    docs_dir = repo / "docs"
    docs_dir.mkdir(exist_ok=True)

    moves = []
    for c in candidates:
        target = c["suggested_target"]
        if not target or target == "inline merge":
            continue  # Skip merge candidates — manual review needed

        # Determine target file
        if target.startswith("docs/"):
            target_path = repo / target
        else:
            # Generate a filename from the heading
            safe_name = re.sub(r"[^a-z0-9]+", "-", c["heading"].lower()).strip("-")
            target_path = docs_dir / f"{safe_name}.md"
            target = f"docs/{safe_name}.md"

        heading = c["heading"]
        heading_marker = "#" * c["level"]

        # Build the content to write
        section_content = f"{heading_marker} {heading}\n\n"
        section_content += c["content_preview"].rstrip("...\n") + "\n\n"
        section_content += f"> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`\n"
        section_content += f"> Date: {datetime.now(timezone.utc).isoformat()}\n"

        # Append to target file (create if doesn't exist)
        if target_path.exists():
            existing = target_path.read_text(encoding="utf-8")
            section_content = existing + "\n\n---\n\n" + section_content

        target_path.write_text(section_content, encoding="utf-8")
        moves.append({"from": f"AGENTS.md → {heading}", "to": str(target), "size": c["lines"]})

    # Now rebuild AGENTS.md with flagged sections replaced by links
    # IMPORTANT: parse_sections stores heading lines separately from content lines.
    # We must re-emit the heading line for sections we keep.
    sections = parse_sections(content)
    new_lines = []
    removed = set(c["heading"] for c in candidates if c["suggested_target"] and c["suggested_target"] != "inline merge")
    heading_preamble = "# Agent Guidelines — Hermes Cortex"  # file-level H1, kept

    for heading, level, lines in sections:
        if heading in removed:
            # Replace heading + content with a brief link
            target = None
            for c in candidates:
                if c["heading"] == heading:
                    target = c["suggested_target"]
                    break
            if target:
                safe_name = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
                link = f"docs/{safe_name}.md" if not target.startswith("docs/") else target
                new_lines.append(f"{'#' * level} {heading}")
                new_lines.append("")
                new_lines.append(f"> Content relocated to [`{link}`]({link}) for focused reference.")
                new_lines.append(f"> _Pruned by agents-doc-audit.py — the full content is preserved at the link above._")
                new_lines.append("")
            else:
                # Shouldn't happen but fallback
                heading_marker = "#" * level
                if heading != "Preamble":
                    new_lines.append(f"{heading_marker} {heading}")
                new_lines.extend(lines)
        else:
            # Keep the heading line + content
            heading_marker = "#" * level
            if heading != "Preamble":
                new_lines.append(f"{heading_marker} {heading}")
            new_lines.extend(lines)

    # Write updated AGENTS.md
    agents_path = repo / "AGENTS.md"
    agents_path.write_text("\n".join(new_lines), encoding="utf-8")

    return {
        "moves": moves,
        "agents_md_path": str(agents_path),
        "total_moved": len(moves),
    }


# ── Sections to check ──────────────────────────────────────────────────────

SECTION_PATTERNS = {
    "Identity": re.compile(r"^##\s+Identity", re.MULTILINE),
    "Core Mission": re.compile(r"^##\s+Core Mission", re.MULTILINE),
    "Behavioral Principles": re.compile(r"^##\s+Behavioral Principles", re.MULTILINE),
    "Loop governance": re.compile(
        r"(?:^###\s+\d+\.\s+Loop governance|loop.governance|mandatory pre-work sequence)",
        re.MULTILINE | re.IGNORECASE,
    ),
    "Inbox Message Decision Framework": re.compile(
        r"(?:^###\s+\d+\.\s+Inbox Message|Inbox Message Decision Framework|decision framework|inbox message decision)",
        re.MULTILINE | re.IGNORECASE,
    ),
    "Communication Style": re.compile(r"^##\s+Communication Style", re.MULTILINE),
    "Agent Execution Contract": re.compile(
        r"^##\s+Agent Execution Contract", re.MULTILINE
    ),
    "Doc Freshness": re.compile(
        r"(?:Doc Freshness|agents-doc-audit|SOUL\.md.*update|AGENTS\.md.*update)",
        re.MULTILINE | re.IGNORECASE,
    ),
    "Agent Cron Management": re.compile(
        r"(?:Agent Cron Management|CRON.*create.*update.*remove|cron-management skill)",
        re.MULTILINE | re.IGNORECASE,
    ),
    "Governance lock": re.compile(
        r"(?:begin_change|end_change|governance.lock|governance-active)",
        re.MULTILINE | re.IGNORECASE,
    ),
    "Rule #10: Score Every Change": re.compile(
        r"(?:Rule #10|Score Every Change|score.change|loop governance.*score)",
        re.MULTILINE | re.IGNORECASE,
    ),
    "Real execution, no simulation": re.compile(
        r"(?:Real execution|no simulation|verified.*result|actual.*command)",
        re.MULTILINE | re.IGNORECASE,
    ),
    "Pre-commit / pre-push hooks": re.compile(
        r"(?:pre.commit|pre.push|commit.*hook|SKIP_SCORE)",
        re.MULTILINE | re.IGNORECASE,
    ),
}


def load_config(config_path=None):
    """Load config from YAML file or return defaults."""
    if config_path:
        try:
            import yaml

            with open(os.path.expanduser(config_path)) as f:
                return yaml.safe_load(f)
        except ImportError:
            print("WARNING: PyYAML not installed, using defaults", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: Failed to load config {config_path}: {e}", file=sys.stderr)
    return DEFAULT_CONFIG


def expand_path(path):
    """Expand ~ and env vars in path."""
    return os.path.expanduser(os.path.expandvars(path))


def read_file_safe(path):
    """Read file content, return None if missing."""
    full_path = expand_path(path)
    try:
        with open(full_path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except PermissionError:
        return f"⚠️  Permission denied: {full_path}"


def check_section(content, section_name):
    """Check if a mandatory section exists in the file content."""
    pattern = SECTION_PATTERNS.get(section_name)
    if pattern:
        return bool(pattern.search(str(content)))
    # Fallback: search for heading-like pattern
    return bool(re.search(
        rf"^##+\s+.*{re.escape(section_name)}", str(content), re.MULTILINE | re.IGNORECASE
    ))


def check_git_freshness(file_path):
    """Check when the file was last modified in git vs on disk."""
    full_path = expand_path(file_path)
    if not os.path.exists(full_path):
        return {"exists": False, "git_date": None, "disk_date": None}

    # Get git directory
    git_dir = os.path.dirname(full_path)
    while git_dir and not os.path.exists(os.path.join(git_dir, ".git")):
        parent = os.path.dirname(git_dir)
        if parent == git_dir:
            git_dir = None
            break
        git_dir = parent

    disk_mtime = datetime.fromtimestamp(os.path.getmtime(full_path), tz=timezone.utc)

    result = {
        "exists": True,
        "disk_date": disk_mtime.isoformat(),
        "git_date": None,
        "stale": False,
    }

    if git_dir:
        try:
            import subprocess

            rel_path = os.path.relpath(full_path, git_dir)
            r = subprocess.run(
                ["git", "log", "-1", "--format=%ai", "--", rel_path],
                capture_output=True,
                text=True,
                cwd=git_dir,
                timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                result["git_date"] = r.stdout.strip()
                # Compare disk vs git
                git_dt = datetime.strptime(
                    r.stdout.strip().split(" ")[0] + "T" + r.stdout.strip().split(" ")[1],
                    "%Y-%m-%dT%H:%M:%S",
                ).replace(tzinfo=timezone.utc)
                # Stale if disk is older than latest git commit for that file
                result["stale"] = disk_mtime < git_dt
        except Exception:
            pass

    return result


def audit():
    """Run the audit and return results dict."""
    parser = argparse.ArgumentParser(description="Audit AGENTS.md and SOUL.md freshness")
    parser.add_argument("--config", help="Path to YAML config file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--send-report",
        action="store_true",
        help="Deliver report via agent inbox (requires MCP tools)",
    )
    parser.add_argument(
        "--repo",
        help="Quick mode: check only AGENTS.md at repo root (for pre-commit hooks). "
             "Exit codes: 0=clean, 1=missing required sections, 2=file not found",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Analyze AGENTS.md for pruning candidates (requires --repo). "
             "Dry-run by default — shows what would be moved.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply pruning moves (requires --prune and --repo). "
             "Moves flagged sections to docs/ and replaces with links.",
    )
    args = parser.parse_args()

    # ── Prune mode ──────────────────────────────────────────────────
    if args.prune:
        if not args.repo:
            print("❌ --prune requires --repo to identify which AGENTS.md to analyze")
            sys.exit(2)

        repo = os.path.expanduser(args.repo)
        config = load_config(args.config)
        protected_list = config.get("protected_sections", DEFAULT_CONFIG.get("protected_sections", []))
        agents_path = os.path.join(repo, "AGENTS.md")
        content = read_file_safe(agents_path)

        if content is None:
            print(f"❌ AGENTS.md not found at {agents_path}")
            sys.exit(2)

        report = generate_pruning_report(repo, content, protected_list, config)

        if args.apply:
            result = apply_pruning(repo, content, report["candidates"], config)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"✅ Pruning applied: {result['total_moved']} sections moved to docs/")
                for m in result["moves"]:
                    print(f"   └ {m['from']} → {m['to']}")
                print(f"\n   Updated: {result['agents_md_path']}")
        else:
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(format_pruning_report(report))

        # Exit: 2 if candidates found, 0 if clean
        if report["candidate_count"] > 0:
            sys.exit(2 if not args.apply else 0)
        sys.exit(0)

    # ── Quick mode (--repo): single AGENTS.md check for pre-commit hooks ─
    if args.repo:
        repo = os.path.expanduser(args.repo)
        agents_path = os.path.join(repo, "AGENTS.md")
        content = read_file_safe(agents_path)
        if content is None or content.startswith("⚠️"):
            msg = f"❌ AGENTS.md not found at {agents_path}" if content is None else content
            if args.json:
                print(json.dumps({"error": msg, "exit_code": 2}))
            else:
                print(msg)
            sys.exit(2)

        # Check hook-required sections (from config, or default list)
        config = load_config(args.config)
        hook_sections = config.get("hook_sections", DEFAULT_CONFIG.get("hook_sections", [
            "Agent Execution Contract",
            "Rule #10: Score Every Change",
            "Real execution, no simulation",
            "Pre-commit / pre-push hooks",
        ]))
        missing = []
        for section in hook_sections:
            if not check_section(content, section):
                missing.append(section)

        if missing:
            if args.json:
                print(json.dumps({
                    "status": "fail",
                    "agents_path": agents_path,
                    "missing_sections": missing,
                    "exit_code": 1,
                }))
            else:
                print(f"⚠️  AGENTS.md at {agents_path} is missing required sections:")
                for s in missing:
                    print(f"   - {s}")
                print("   Add them before committing, or use SKIP_SCORE=1 to bypass.")
            sys.exit(1)

        if args.json:
            print(json.dumps({"status": "ok", "agents_path": agents_path, "exit_code": 0}))
        else:
            print(f"✅ AGENTS.md at {agents_path} — all required sections present")
        sys.exit(0)

    config = load_config(args.config)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "soul_audits": [],
        "agents_audits": [],
        "summary": {"passed": 0, "warnings": 0, "errors": 0, "missing_sections": []},
    }

    # ── Check SOUL.md files ────────────────────────────────────────
    for entry in config.get("soul_files", []):
        content = read_file_safe(entry["path"])
        audit_entry = {
            "path": entry["path"],
            "agent": entry.get("agent", "unknown"),
            "exists": content is not None,
            "missing_sections": [],
            "status": "ok",
        }

        if content is None:
            audit_entry["status"] = "error"
            audit_entry["note"] = "File not found"
            results["summary"]["errors"] += 1
        elif content.startswith("⚠️"):
            audit_entry["status"] = "error"
            audit_entry["note"] = content
            results["summary"]["errors"] += 1
        else:
            for section in entry.get("mandatory_sections", []):
                if not check_section(content, section):
                    audit_entry["missing_sections"].append(section)
                    results["summary"]["missing_sections"].append(
                        f"{entry.get('agent', '?')} → {entry['path']}: missing '{section}'"
                    )

            if audit_entry["missing_sections"]:
                audit_entry["status"] = "warning"
                results["summary"]["warnings"] += 1
            else:
                audit_entry["status"] = "ok"
                results["summary"]["passed"] += 1

            # Check git freshness
            freshness = check_git_freshness(entry["path"])
            audit_entry["freshness"] = freshness
            if freshness.get("stale"):
                audit_entry["status"] = "warning"
                audit_entry["note"] = "Disk copy older than last git commit"

        results["soul_audits"].append(audit_entry)

    # ── Check AGENTS.md files ──────────────────────────────────────
    for entry in config.get("agents_files", []):
        content = read_file_safe(entry["path"])
        audit_entry = {
            "path": entry["path"],
            "repo": entry.get("repo", "unknown"),
            "exists": content is not None,
            "missing_sections": [],
            "status": "ok",
        }

        if content is None:
            audit_entry["status"] = "error"
            audit_entry["note"] = "File not found"
            results["summary"]["errors"] += 1
        elif content.startswith("⚠️"):
            audit_entry["status"] = "error"
            audit_entry["note"] = content
            results["summary"]["errors"] += 1
        else:
            for section in entry.get("mandatory_sections", []):
                if not check_section(content, section):
                    audit_entry["missing_sections"].append(section)
                    results["summary"]["missing_sections"].append(
                        f"{entry.get('repo', '?')} → {entry['path']}: missing '{section}'"
                    )

            if audit_entry["missing_sections"]:
                audit_entry["status"] = "warning"
                results["summary"]["warnings"] += 1
            else:
                audit_entry["status"] = "ok"
                results["summary"]["passed"] += 1

        freshness = check_git_freshness(entry["path"])
        audit_entry["freshness"] = freshness
        if freshness.get("stale"):
            audit_entry["status"] = "warning"

        results["agents_audits"].append(audit_entry)

    return results, args.json, args.send_report


def format_report(results):
    """Format audit results as a human-readable report string."""
    lines = []
    lines.append("📋 **AGENTS.md + SOUL.md Freshness Audit**")
    lines.append(f"🕐 {results['timestamp']}")
    lines.append("")

    summary = results["summary"]
    emoji = "✅" if summary["errors"] == 0 and summary["warnings"] == 0 else "⚠️" if summary["warnings"] > 0 else "❌"
    lines.append(f"{emoji} **Summary:** {summary['passed']} passed, {summary['warnings']} warnings, {summary['errors']} errors")
    lines.append("")

    # SOUL.md section
    if results["soul_audits"]:
        lines.append("**📜 SOUL.md files:**")
        for a in results["soul_audits"]:
            icon = {"ok": "✅", "warning": "⚠️", "error": "❌"}.get(a["status"], "❓")
            lines.append(f"{icon} **{a['agent']}** → `{a['path']}`")
            if a["status"] == "error":
                lines.append(f"   └ {a.get('note', 'File not found or unreadable')}")
            if a["missing_sections"]:
                lines.append(f"   └ Missing: {', '.join(a['missing_sections'])}")
            if a.get("freshness", {}).get("stale"):
                lines.append(f"   └ ⏳ Disk copy stale (git has newer version)")
        lines.append("")

    # AGENTS.md section
    if results["agents_audits"]:
        lines.append("**📋 AGENTS.md files:**")
        for a in results["agents_audits"]:
            icon = {"ok": "✅", "warning": "⚠️", "error": "❌"}.get(a["status"], "❓")
            lines.append(f"{icon} **{a['repo']}** → `{a['path']}`")
            if a["missing_sections"]:
                lines.append(f"   └ Missing: {', '.join(a['missing_sections'])}")
            if a.get("freshness", {}).get("stale"):
                lines.append(f"   └ ⏳ Modified locally but git has newer version")
        lines.append("")

    # Details
    if summary["missing_sections"]:
        lines.append("**📝 Action Items:**")
        for item in summary["missing_sections"]:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def main():
    results, as_json, send_report = audit()

    report = format_report(results)

    if as_json:
        print(json.dumps(results, indent=2))
    else:
        print(report)

    # If --send-report, output a marker for the cron to detect
    if send_report:
        print("\n---SEND-REPORT---")
        print(f"Subject: Agents Doc Audit: {results['summary']['errors']} errors, {results['summary']['warnings']} warnings")
        print(report)
        print("---END-REPORT---")

    # Exit code: 0 = all clean, 1 = warnings, 2 = errors
    if results["summary"]["errors"] > 0:
        sys.exit(2)
    if results["summary"]["warnings"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
