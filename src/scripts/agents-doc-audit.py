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
}

# Sections to check. A section is considered present if:
# - Heading with that text exists, OR
# - The text appears as a significant anchor in the document
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
            # Use git log to find last commit touching this file
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
    args = parser.parse_args()

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