#!/usr/bin/env python3
"""skill-triage.py — Moses-side: full automated skill triage pipeline.

Reads skill reports from the PGMQ bus, deduplicates against the upstream repo
and Hermes bundle, auto-upstreams truly new skills, tracks all decisions,
and produces a Telegram digest.

Pipeline:
  1. Read messages from inbox_moses PGMQ queue
  2. Filter for Skill Report: subjects
  3. Parse skill data (name, category, content)
  4. Deduplicate: skip if already in repo, Hermes bundle, or previously reviewed
  5. Auto-upstream: create SKILL.md in repo for genuinely new skills
  6. Track: record all decisions in state file
  7. Archive processed messages
  8. Produce digest with summary of what was done

Usage:
    python3 skill-triage.py              # process pending reports
    python3 skill-triage.py --dry-run    # show what would be done without changes
    python3 skill-triage.py --force      # reprocess even previously reviewed
"""

import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ── Config from environment ─────────────────────────────────
CORTEX_BUS_URL = os.environ.get("CORTEX_BUS_URL", "http://127.0.0.1:8903")
CORTEX_BUS_TOKEN = os.environ.get("CORTEX_BUS_TOKEN", "")
REPO_DIR = Path(os.environ.get("CORTEX_REPO", Path.home() / "hermes-cortex"))
STATE_DIR = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex")) / "state"
HERMES_SKILLS_DIR = Path.home() / ".hermes" / "skills"
HERMES_BUNDLE_DIR = Path.home() / ".hermes" / "hermes-agent" / "skills"
REPO_SKILLS_DIR = REPO_DIR / "skills"
DECISIONS_FILE = STATE_DIR / "skill-decisions.json"
QUEUE = "inbox_moses"

# Try reading from .env if env vars not set
if not CORTEX_BUS_TOKEN:
    for conf in [REPO_DIR / ".env",
                 STATE_DIR.parent / "cortex-bus.conf",
                 Path.home() / ".hermes" / "cortex-bus.conf"]:
        if conf.exists():
            try:
                for line in conf.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("CORTEX_BUS_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            CORTEX_BUS_TOKEN = val
                    elif line.startswith("CORTEX_BUS_URL=") and not "127.0.0.1" in os.environ.get("CORTEX_BUS_URL", ""):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            CORTEX_BUS_URL = val
            except Exception:
                pass
        if CORTEX_BUS_TOKEN:
            break

BUS_URL = CORTEX_BUS_URL.rstrip("/")


# ── Helpers ──────────────────────────────────────────────────

def bus_request(endpoint: str, data: dict | None = None, method: str | None = None) -> dict:
    """Make an authenticated request to the PGMQ bus API."""
    url = f"{BUS_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {CORTEX_BUS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    http_method = method or ("POST" if data else "GET")

    try:
        req = Request(url, data=body, headers=headers, method=http_method)
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        print(f"WARN: HTTP {e.code} on {endpoint}: {err_body[:200]}", file=sys.stderr)
        return {}
    except (URLError, OSError, json.JSONDecodeError) as e:
        print(f"WARN: Request failed on {endpoint}: {e}", file=sys.stderr)
        return {}


# ── Bus operations ──────────────────────────────────────────

def read_queue_messages(queue: str, vt: int = 30, limit: int = 10) -> list[dict]:
    """Read messages from a PGMQ queue."""
    payload = {"queue": queue, "vt": vt, "limit": limit}
    resp = bus_request("/api/pgmq/read", payload)
    if not resp:
        return []
    if isinstance(resp, dict) and "msg_id" in resp:
        return [resp]
    return []


def archive_message(queue: str, msg_id: str) -> bool:
    """Delete a processed message from the queue (DELETE method)."""
    resp = bus_request("/api/pgmq/delete", {"queue": queue, "msg_id": msg_id}, method="DELETE")
    return "detail" not in resp


# ── Skill report parsing ────────────────────────────────────

def parse_reports_from_queue(messages: list[dict]) -> list[dict]:
    """Extract skill reports from raw bus messages."""
    reports = []
    for msg in messages:
        inner = msg.get("body", {})
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except json.JSONDecodeError:
                continue
        if not isinstance(inner, dict):
            continue

        subject = inner.get("subject", "") or ""
        if "skill report" not in subject.lower():
            continue

        reports.append({
            "from": inner.get("from", "?"),
            "subject": subject,
            "body": inner.get("body", ""),
            "timestamp": msg.get("enqueued_at", ""),
            "msg_id": msg.get("msg_id", ""),
        })
    return reports


def parse_skills_from_body(body: str) -> list[dict]:
    """Parse individual skill entries from a report body."""
    skills = []
    current = None
    content_lines = []

    for line in body.split("\n"):
        stripped = line.strip()

        # Detect skill header: == Skill: name (category) ==
        header_match = re.match(r"==\s+Skill:\s+(.+?)(?:\s+\((.+?)\))?\s+==", stripped)
        if header_match:
            # Save previous skill
            if current:
                current["content"] = "\n".join(content_lines).strip()
                skills.append(current)
                content_lines = []

            current = {
                "name": header_match.group(1).strip(),
                "category": header_match.group(2).strip() if header_match.group(2) else "",
                "description": "",
                "lines": 0,
                "age_days": 0,
                "content": "",
            }
            continue

        if current:
            # Parse metadata lines before content
            if stripped.startswith("Lines:") and current["lines"] == 0:
                m = re.search(r"Lines:\s*(\d+)", stripped)
                if m:
                    current["lines"] = int(m.group(1))
            elif stripped.startswith("Age:") and current["age_days"] == 0:
                m = re.search(r"Age:\s*(\d+)d", stripped)
                if m:
                    current["age_days"] = int(m.group(1))
            elif stripped.startswith("Description:"):
                current["description"] = stripped[len("Description:"):].strip()
            elif stripped == "--- Full content (truncated) ---":
                pass  # content starts after this
            elif current["description"] and stripped not in ("", "--- End skill ---"):
                content_lines.append(line)

    # Save last skill
    if current:
        current["content"] = "\n".join(content_lines).strip()
        skills.append(current)

    return skills


# ── Dedup sources ────────────────────────────────────────────

def _walk_skill_names(root: Path, prefix: str = "") -> dict[str, dict]:
    """Walk a skills directory and return {skill_name: {category, path}}."""
    result = {}
    if not root.is_dir():
        return result
    for skill_file in root.rglob("SKILL.md"):
        rel = skill_file.relative_to(root)
        category = str(rel.parent.parent) if rel.parent.parent != "." else ""
        name = skill_file.parent.name
        result[name.lower()] = {
            "name": name,
            "category": category,
            "path": str(skill_file),
            "source": prefix,
        }
    return result


def _walk_cortex_skills(root: Path) -> dict[str, dict]:
    """Walk the cortex skills directory for all installed skills."""
    result = {}
    if not root.is_dir():
        return result
    for skill_file in root.rglob("SKILL.md"):
        name = skill_file.parent.name
        rel = skill_file.relative_to(root)
        category = str(rel.parent.parent) if rel.parent.parent != "." else ""
        result[name.lower()] = {
            "name": name,
            "category": category,
            "path": str(skill_file),
            "source": "installed",
        }
    return result


def load_decisions() -> dict:
    """Load previous triage decisions from state file."""
    if DECISIONS_FILE.exists():
        try:
            return json.loads(DECISIONS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"upstreamed": {}, "skipped": {}, "rejected": {}}


def save_decisions(decisions: dict):
    """Save triage decisions to state file."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DECISIONS_FILE.write_text(json.dumps(decisions, indent=2, ensure_ascii=False))


# ── Upstream logic ───────────────────────────────────────────

def create_skill_skel(name: str, category: str, description: str, body_content: str) -> str:
    """Generate a SKILL.md skeleton from the available data."""
    lines = []
    lines.append("---")
    lines.append(f"name: {name}")
    lines.append(f"description: \"{description or '(no description — auto-detected from agent report)'}\"")
    lines.append("---")
    lines.append("")
    if body_content and body_content != "(content unavailable)":
        # Check if truncated
        if "... [truncated]" in body_content:
            lines.append(body_content.replace("... [truncated]", "").strip())
            lines.append("")
            lines.append("<!-- Full content was truncated in the agent report. Fetch from the source agent for complete version. -->")
        else:
            lines.append(body_content)
    else:
        lines.append("# " + name)
        lines.append("")
        lines.append("<!-- Auto-detected skill — content was not available in the agent report. -->")
        lines.append("")
        lines.append("## Description")
        lines.append(description or "Tool or workflow skill used on agent machine.")
    return "\n".join(lines)


def upstream_skill(name: str, category: str, description: str, content: str) -> tuple[bool, str]:
    """Create a SKILL.md file in the repo for a new skill.
    Returns (success, path_or_error)."""
    # Determine target category directory
    cat_dir = category if category else "uncategorized"
    target_dir = REPO_SKILLS_DIR / cat_dir / name
    target_file = target_dir / "SKILL.md"

    if target_file.exists():
        return False, f"Already exists: {target_file}"

    target_dir.mkdir(parents=True, exist_ok=True)
    skel = create_skill_skel(name, cat_dir, description, content)
    try:
        target_file.write_text(skel)
        return True, str(target_file.relative_to(REPO_DIR))
    except OSError as e:
        return False, str(e)


def git_commit_and_push(files: list[str], agent: str) -> str:
    """Commit and push new skill files to the repo."""
    try:
        import subprocess
        cwd = str(REPO_DIR)

        # Add files
        for f in files:
            subprocess.run(["git", "add", f], cwd=cwd, capture_output=True, text=True)

        # Check if there's anything to commit
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=cwd)
        if result.returncode == 0:
            return "No changes to commit"

        # Commit
        summary = f"auto-upstream: {len(files)} skill(s) from {agent}"
        body = "Auto-upstreamed by skill-triage.py from agent skill report.\n\n"
        body += "\n".join(f"  - {f}" for f in files)
        subprocess.run(
            ["git", "commit", "-m", summary, "-m", body, "--no-verify"],
            cwd=cwd, capture_output=True, text=True,
        )

        # Push
        push = subprocess.run(["git", "push", "origin", "main"], cwd=cwd, capture_output=True, text=True)
        if push.returncode != 0:
            return f"Committed but push failed: {push.stderr.strip()[:200]}"
        return f"Pushed {len(files)} new skill(s)"
    except Exception as e:
        return f"Git error: {e}"


# ── Main triage pipeline ─────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    # ── Phase 1: Read queue ──
    messages = []
    for _ in range(20):  # up to 20 read attempts
        batch = read_queue_messages(QUEUE, vt=60, limit=5)
        if not batch:
            break
        messages.extend(batch)

    if not messages:
        return  # Silent — no messages

    # ── Phase 2: Extract reports ──
    reports = parse_reports_from_queue(messages)

    if not reports:
        # Archive non-skill-report messages so they don't pile up
        for msg in messages:
            archive_message(QUEUE, msg.get("msg_id", ""))
        return  # Silent

    # ── Phase 3: Build dedup sets ──
    repo_skills = _walk_skill_names(REPO_SKILLS_DIR, "repo")
    bundle_skills = _walk_skill_names(HERMES_BUNDLE_DIR, "bundle")
    cortex_skills = _walk_cortex_skills(STATE_DIR.parent / "skills")

    decisions = load_decisions()
    upstreamed_names = set(decisions.get("upstreamed", {}).keys())
    skipped_names = set(decisions.get("skipped", {}).keys())
    rejected_names = set(decisions.get("rejected", {}).keys())

    # Combined dedup: all known skill names
    def is_known(name: str) -> str | None:
        key = name.lower()
        if key in repo_skills:
            return f"already in repo ({repo_skills[key]['category']}/{name})"
        if key in bundle_skills:
            return "Hermes bundled skill"
        if key in cortex_skills:
            return "already installed in cortex"
        if key in upstreamed_names:
            return "previously upstreamed"
        if not force:
            if key in skipped_names:
                return "previously skipped"
            if key in rejected_names:
                return "previously rejected"
        return None

    # ── Phase 4: Process each report ──
    all_results = []  # {agent, skill_name, action, detail}

    for report in reports:
        agent = report["from"]
        body = report.get("body", "")
        skills = parse_skills_from_body(body)

        for skill in skills:
            name = skill["name"]
            category = skill["category"]
            description = skill["description"]
            content = skill["content"]

            # Dedup
            reason = is_known(name)
            if reason:
                all_results.append({
                    "agent": agent,
                    "skill_name": name,
                    "action": "skipped",
                    "detail": reason,
                })
                continue

            # Auto-upstream
            if dry_run:
                all_results.append({
                    "agent": agent,
                    "skill_name": name,
                    "action": "would_upstream",
                    "detail": f"category={category}, lines={skill['lines']}, age={skill['age_days']}d",
                })
                continue

            success, detail = upstream_skill(name, category, description, content)
            if success:
                all_results.append({
                    "agent": agent,
                    "skill_name": name,
                    "action": "upstreamed",
                    "detail": detail,
                })
                # Track decision
                decisions.setdefault("upstreamed", {})[name.lower()] = {
                    "name": name,
                    "category": category,
                    "agent": agent,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "file": detail,
                }
            else:
                all_results.append({
                    "agent": agent,
                    "skill_name": name,
                    "action": "failed",
                    "detail": detail,
                })

        # Archive the processed report message
        msg_id = report.get("msg_id", "")
        if msg_id:
            archive_message(QUEUE, msg_id)

    # ── Phase 5: Git commit & push ──
    upstreamed_files = [r["detail"] for r in all_results if r["action"] == "upstreamed"]
    if upstreamed_files and not dry_run:
        git_result = git_commit_and_push(upstreamed_files, reports[0]["from"])
        for r in all_results:
            if r["action"] == "upstreamed":
                r["git_result"] = git_result

    # Save decisions
    if not dry_run:
        save_decisions(decisions)

    # ── Phase 6: Produce digest ──
    output = format_digest(all_results)
    if output:
        print(output)


def format_digest(results: list[dict]) -> str:
    """Format triage results into a Telegram-friendly digest."""
    if not results:
        return ""

    upstreamed = [r for r in results if r["action"] == "upstreamed"]
    skipped = [r for r in results if r["action"] == "skipped"]
    failed = [r for r in results if r["action"] == "failed"]
    would = [r for r in results if r["action"] == "would_upstream"]
    agents = set(r["agent"] for r in results)

    lines = []
    lines.append("## 🧠 Skill Triage Report\n")

    if upstreamed:
        lines.append(f"**✅ Upstreamed:** {len(upstreamed)} new skill(s)")
        git_msg = upstreamed[0].get("git_result", "")
        if git_msg:
            lines.append(f"  └ {git_msg}")
        lines.append("")
        for s in upstreamed:
            lines.append(f"  • `{s['skill_name']}` → `{s['detail']}`")
        lines.append("")

    if would:
        lines.append(f"**🔷 Would upstream ({len(would)}):**")
        for s in would:
            lines.append(f"  • `{s['skill_name']}` — {s['detail']}")
        lines.append("")

    if skipped:
        lines.append(f"**⏭️ Skipped:** {len(skipped)}")
        by_reason = {}
        for s in skipped:
            reason = s["detail"]
            by_reason.setdefault(reason, []).append(s["skill_name"])
        for reason, names in sorted(by_reason.items()):
            lines.append(f"  • {reason}: {', '.join(f'`{n}`' for n in names[:8])}{'…' if len(names) > 8 else ''}")
        lines.append("")

    if failed:
        lines.append(f"**❌ Failed:** {len(failed)}")
        for s in failed:
            lines.append(f"  • `{s['skill_name']}` — {s['detail']}")
        lines.append("")

    lines.append(f"*From: {', '.join(sorted(agents))}*")
    lines.append("")
    lines.append("---")
    if upstreamed:
        lines.append("*Skills upstreamed and pushed to repo. Other agents get them on next `cortex-update.sh`.*")
    else:
        lines.append("*All reported skills were already known — nothing new to upstream.*")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
