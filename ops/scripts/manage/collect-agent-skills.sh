#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  collect-agent-skills.sh — Agent-side skill manifest reporter
#
#  Scans BOTH ~/.hermes/skills/ (Hermes native) AND
#  ~/.hermes-cortex/skills/ (cortex deploy) for SKILL.md files
#  that are NOT from the upstream hermes-cortex repo and
#  reports them as custom skills to Moses via inbox.
#
#  The entire scan + JSON build is done in Python to correctly
#  handle special characters, multi-line content, and JSON encoding.
#
#  no_agent-safe: silent exit (0) when nothing new to report.
#
#  Requires (from ~/hermes-cortex/.env):
#    CORTEX_BUS_URL      — Moses Agent Bus URL
#    CORTEX_BUS_TOKEN    — Bearer token for bus auth
#
#  Deployed to agents via cortex-update.sh.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="${CORTEX_REPO:-$HOME/hermes-cortex}"
HERMES_SKILLS_DIR="$HOME/.hermes/skills"
CORTEX_SKILLS_DIR="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}/skills"
REPO_SKILLS_DIR="$REPO_DIR/.hermes-cortex/skills"
# Also check bundled Hermes Agent skills (not truly "custom")
HERMES_BUNDLED_SKILLS_DIR="$HOME/.hermes/hermes-agent/skills"
STATE_DIR="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}/state"
MANIFEST_FILE="$STATE_DIR/skills-manifest.json"

# ── Source config ───────────────────────────────────────────
if [[ -f "${HOME}/hermes-cortex/.env" ]]; then
  set -a; source "${HOME}/hermes-cortex/.env"; set +a
elif [[ -f "${HOME}/.hermes-cortex/hermes-inbox.conf" ]]; then
  source "${HOME}/.hermes-cortex/hermes-inbox.conf"
fi

# ── Build manifest via Python ──────────────────────────────
# (Python handles JSON encoding, multi-line content, and
#  special characters correctly. Bash cannot safely build JSON.)
mkdir -p "$STATE_DIR"

# Export vars for Python subprocess
export STATE_DIR HERMES_SKILLS_DIR CORTEX_SKILLS_DIR REPO_SKILLS_DIR HERMES_BUNDLED_SKILLS_DIR

python3 << 'PYEOF'
import json, os, time
from pathlib import Path

state_dir = Path(os.environ["STATE_DIR"])
hermes_skills = Path(os.environ["HERMES_SKILLS_DIR"])
cortex_skills = Path(os.environ["CORTEX_SKILLS_DIR"])
repo_skills = Path(os.environ["REPO_SKILLS_DIR"])
bundled_skills = Path(os.environ.get("HERMES_BUNDLED_SKILLS_DIR", ""))
manifest_file = state_dir / "skills-manifest.json"
contents_dir = state_dir / "skill-contents"
contents_dir.mkdir(parents=True, exist_ok=True)

# Load skill ignore list (one skill name per line, # comments supported)
ignore_file = state_dir / "skill-ignore.txt"
ignored_skills = set()
if ignore_file.exists():
    for line in ignore_file.read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            ignored_skills.add(line.lower())
hostname = os.uname().nodename
timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

skills_list = []
seen_paths = set()

def scan_dir(search_dir):
    """Scan a directory for SKILL.md files not in the upstream repo."""
    if not search_dir.is_dir():
        return
    for skill_file in sorted(search_dir.rglob("SKILL.md")):
        if not skill_file.is_file():
            continue
        rel_path = str(skill_file.relative_to(search_dir))
        if rel_path in seen_paths:
            continue
        seen_paths.add(rel_path)

        # Skip if this skill exists in the upstream repo
        repo_path = repo_skills / rel_path
        if repo_path.exists():
            continue

        # Skip if this skill exists in the Hermes Agent bundle
        if bundled_skills.is_dir():
            bundled_path = bundled_skills / rel_path
            if bundled_path.exists():
                continue

        text = skill_file.read_text(errors="replace")
        name = skill_file.parent.name

        # Skip if in the ignore list (personal/private skills)
        if name.lower() in ignored_skills:
            continue

        parent = skill_file.parent.parent
        try:
            category = str(parent.relative_to(search_dir))
        except ValueError:
            category = ""

        lines_count = text.count("\n") + 1

        # Extract description from YAML frontmatter
        summary = "(no description)"
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                front = text[3:end]
                for line in front.split("\n"):
                    line = line.strip()
                    if line.startswith("description:"):
                        desc = line[len("description:"):].strip().strip("'\"")
                        if desc and desc not in ("|", ">"):
                            summary = desc
                        break

        # File age in days
        try:
            stat = skill_file.stat()
            birth = getattr(stat, 'st_birthtime', stat.st_ctime)
        except Exception:
            birth = skill_file.stat().st_ctime
        age_days = max(0, int((time.time() - birth) / 86400))

        skills_list.append({
            "name": name,
            "category": category,
            "lines": lines_count,
            "age_days": age_days,
            "summary": summary,
        })

        # Write full content to individual file
        idx = len(skills_list) - 1
        (contents_dir / f"idx_{idx}.txt").write_text(text)

scan_dir(hermes_skills)
scan_dir(cortex_skills)

manifest = {
    "sender": hostname,
    "type": "skill-report",
    "generated": timestamp,
    "total_skills": len(seen_paths),
    "custom_skills": len(skills_list),
    "skills": skills_list,
}

manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
total = len(skills_list)
if total > 0:
    print(f"FOUND {total} custom skills", flush=True)
PYEOF

# ── Read results from Python output ─────────────────────────
# Python prints "FOUND N custom skills" when there are custom skills
# If Python exited silently (no output), there are 0 custom skills
PY_OUTPUT=$(tail -1 /dev/null 2>/dev/null || true)
# Actually Python's print goes to stdout which bash captures. Let's use a temp file.
TOTAL_FILE="$STATE_DIR/.custom_skill_count"
python3 -c "import json; print(json.load(open('$MANIFEST_FILE')).get('custom_skills', 0))" > "$TOTAL_FILE"
TOTAL=$(cat "$TOTAL_FILE" 2>/dev/null || echo 0)

# ── Silent exit when nothing to report (watchdog pattern) ──
if [[ "$TOTAL" -eq 0 ]]; then
  exit 0
fi

# ── Send to Moses inbox via JSON API ────────────────────────
BUS_URL="${CORTEX_BUS_FALLBACK_URL:-${CORTEX_INBOX_URL:-}}"
if [[ -n "$BUS_URL" ]]; then
  # Export vars for Python subprocess
  export STATE_DIR

  python3 << 'PYEOF'
import json, os, sys, urllib.request, urllib.error, base64, time
from pathlib import Path

state_dir = Path(os.environ["STATE_DIR"])
manifest_file = state_dir / "skills-manifest.json"
contents_dir = state_dir / "skill-contents"
inbox_url = (os.environ.get("CORTEX_BUS_FALLBACK_URL", "") or os.environ.get("CORTEX_INBOX_URL", "")).rstrip("/") + "/api/send"
auth_creds = os.environ.get("CORTEX_BUS_AUTH", "") or os.environ.get("CORTEX_INBOX_AUTH", "")

if not manifest_file.exists():
    exit(0)

manifest = json.loads(manifest_file.read_text())
custom_total = manifest.get("custom_skills", 0)
if custom_total == 0:
    exit(0)

# Read skill contents from individual files
contents = []
if contents_dir.is_dir():
    for i in range(len(manifest.get("skills", []))):
        cf = contents_dir / f"idx_{i}.txt"
        contents.append(cf.read_text() if cf.exists() else "")

hostname = os.uname().nodename

# Build body text
parts = []
parts.append(f"━━━ Skill Report — {manifest.get('sender', hostname)} ━━━")
parts.append(f"Generated: {manifest.get('generated', '')}")
parts.append(f"Total skills installed: {manifest.get('total_skills', 0)}")
parts.append(f"Custom skills (not upstream): {custom_total}")
parts.append("")

for i, s in enumerate(manifest.get("skills", [])):
    name = s.get("name", "?")
    catg = s.get("category", "")
    tag = f" ({catg})" if catg else ""
    parts.append(f"== Skill: {name}{tag} ==")
    parts.append(f"Lines: {s.get('lines', 0)} | Age: {s.get('age_days', 0)}d")
    parts.append(f"Description: {s.get('summary', '')}")
    parts.append("")
    parts.append("--- Full content (truncated) ---")
    content = contents[i] if i < len(contents) else "(content unavailable)"
    if len(content) > 1000:
        parts.append(content[:1000] + "\n... [truncated]")
    else:
        parts.append(content)
    parts.append("--- End skill ---")
    parts.append("")

body_text = "\n".join(parts)
payload = {
    "from": hostname,
    "subject": f"Skill Report: {custom_total} custom skills",
    "body": body_text,
    "topic": "reports",
    "priority": "normal",
}

req = urllib.request.Request(
    inbox_url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
if auth_creds and ":" in auth_creds:
    encoded = base64.b64encode(auth_creds.encode()).decode()
    req.add_header("Authorization", f"Basic {encoded}")

try:
    resp = urllib.request.urlopen(req, timeout=30)
    print(f"Sent {custom_total} custom skills to Moses inbox", flush=True)
except urllib.error.HTTPError as e:
    if e.code == 413:
        print(f"WARN: Report too large ({len(body_text)} bytes, max 100KB) — will be split in next run", file=sys.stderr, flush=True)
        # Save the count for the record but don't retry
        print(f"WARN: {custom_total} custom skills found but not sent (too large)", file=sys.stderr, flush=True)
    else:
        print(f"WARN: HTTP {e.code} sending skill report: {e}", file=sys.stderr, flush=True)
    exit(0)  # Non-fatal — will retry next cycle
except urllib.error.URLError as e:
    print(f"WARN: Failed to send skill report: {e}", file=sys.stderr, flush=True)
    exit(1)
PYEOF
fi
