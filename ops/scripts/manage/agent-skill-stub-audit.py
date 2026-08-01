#!/usr/bin/env python3
"""agent-skill-stub-audit.py — Fleet-side audit for truncated skill recovery.

The Jul-17 skill imports (9a9efa91, 2347d26a, 70160929) landed in the repo
as ~1KB stubs because the old collector truncated bus messages at 1000 chars.
Agents' LOCAL copies were always full: both ~/.hermes/skills/<cat>/<name>/SKILL.md
AND the collector's state/skill-contents/idx_N.txt cache.

This script scans the local machine for FULL copies of the stubbed skills and
sends them to Moses via the bus. AGENTS DO NOT WRITE THE REPO — they only
send; Moses (the orchestrator) collects the messages and restores the full
content into skills/ on the repo side.

Naming: agent-* prefix (fleet-wide — runs on every agent).

Usage:
    python3 agent-skill-stub-audit.py                    # scan, print recoverable
    python3 agent-skill-stub-audit.py --send             # bus-send full copies to Moses

Exit codes: 0 = found recoverable content, 1 = nothing, 2 = error
"""
import json
import os
import sys
from pathlib import Path

HOME = Path.home()
HERMES_SKILLS = HOME / ".hermes" / "skills"
CORTEX_SKILLS = HOME / ".hermes-cortex" / "skills"
STATE_DIR = HOME / ".hermes-cortex" / "state"

STUB_MARKER = "Full content (truncated)"
MIN_FULL_SIZE = 1500  # stubs are ~1KB; anything bigger is likely full

# The 131 stubbed skill names (from repo census) — passed via env var to keep
# this script generic; fall back to scanning everything for >1KB files.
STUB_NAMES = set()
env_names = os.environ.get("SKILL_STUB_NAMES", "")
if env_names:
    STUB_NAMES = set(n.strip() for n in env_names.split(",") if n.strip())


def is_stub(content: str) -> bool:
    return STUB_MARKER in content or (content and "End skill ---" in content and len(content) < 1500)


def scan_skills_dir(d: Path) -> dict:
    """Return {skill_name: full_content} for SKILL.md files that are NOT stubs."""
    found = {}
    if not d.is_dir():
        return found
    for f in sorted(d.rglob("SKILL.md")):
        try:
            text = f.read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        if is_stub(text):
            continue
        if len(text) < MIN_FULL_SIZE:
            continue
        name = f.parent.name
        if STUB_NAMES and name not in STUB_NAMES:
            continue
        # prefer the bigger/full one
        if name not in found or len(text) > len(found[name]):
            found[name] = text
    return found


def scan_state_cache() -> dict:
    """Collector's skill-contents cache: manifest maps idx_N -> skill."""
    found = {}
    manifest_file = STATE_DIR / "skills-manifest.json"
    if not manifest_file.exists():
        return found
    try:
        manifest = json.loads(manifest_file.read_text())
    except (OSError, json.JSONDecodeError):
        return found
    contents_dir = STATE_DIR / "skill-contents"
    for i, s in enumerate(manifest.get("skills", [])):
        name = s.get("name", "")
        if not name or (STUB_NAMES and name not in STUB_NAMES):
            continue
        f = contents_dir / f"idx_{i}.txt"
        if not f.exists():
            continue
        text = f.read_text(errors="replace")
        if is_stub(text) or len(text) < MIN_FULL_SIZE:
            continue
        found[name] = text
    return found


def main():
    send = "--send" in sys.argv
    found = {}
    for d in (HERMES_SKILLS, CORTEX_SKILLS):
        found.update(scan_skills_dir(d))
    found.update(scan_state_cache())

    if not found:
        print(json.dumps({"recoverable": 0, "skills": {}}, indent=2))
        return 1

    report = {
        "hostname": os.uname().nodename,
        "recoverable": len(found),
        "skills": {name: len(content) for name, content in found.items()},
    }
    print(json.dumps(report, indent=2))

    if send:
        # bus-send the full contents back to Moses inbox — CHUNKED (90KB cap,
        # same pattern as agent-collect-skills.sh). One message per chunk.
        try:
            from lib.cortex_bus import bus_send  # deployed alongside
        except ImportError:
            sys.path.insert(0, str(HOME / ".hermes-cortex" / "scripts"))
            try:
                from lib.cortex_bus import bus_send
            except ImportError:
                print("WARN: lib.cortex_bus not found — cannot send", file=sys.stderr)
                return 2

        MAX_BODY_BYTES = 90_000
        items = [{"name": n, "content": c} for n, c in sorted(found.items())]
        chunks, cur, cur_size = [], [], 0
        for it in items:
            block = json.dumps(it, ensure_ascii=False)
            if cur and cur_size + len(block) > MAX_BODY_BYTES:
                chunks.append(cur)
                cur, cur_size = [], 0
            cur.append(it)
            cur_size += len(block)
        if cur:
            chunks.append(cur)

        ok_all = True
        for ci, chunk in enumerate(chunks):
            payload = {
                "type": "skill-stub-recovery",
                "hostname": os.uname().nodename,
                "part": ci + 1,
                "parts": len(chunks),
                "skills": {it["name"]: it["content"] for it in chunk},
            }
            ok = bus_send(
                "inbox_moses",
                {
                    "from": os.uname().nodename,
                    "subject": f"Skill Stub Recovery (part {ci + 1}/{len(chunks)})",
                    "body": payload,
                    "topic": "reports",
                    "priority": "normal",
                },
            )
            ok_all = ok_all and bool(ok)
        print(f"SENT: {ok_all} ({len(chunks)} parts)" if ok_all else "SEND FAILED", file=sys.stderr)
        return 0 if ok_all else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
