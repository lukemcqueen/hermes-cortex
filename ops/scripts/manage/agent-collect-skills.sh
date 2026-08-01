#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  agent-collect-skills.sh — Agent-side skill manifest reporter
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
elif [[ -f "${HOME}/.hermes-cortex/cortex-bus.conf" ]]; then
  source "${HOME}/.hermes-cortex/cortex-bus.conf"
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

# ── Stub-recovery cache (2026-08-02) ─────────────────────
# If the deployed SKILL.md was overwritten by a truncated stub (the Jul-17
# imports landed ~1KB stubs via the old 1000-char bus truncation, then
# cortex-update synced them over the full copies), the previous run's
# skill-contents cache is the ONLY surviving full source. Load it up front
# so a stub read from disk never overwrites full content in the report.
existing_full_cache = {}  # skill_name -> full content from previous run
_old_manifest_file = state_dir / "skills-manifest.json"
if _old_manifest_file.exists():
    try:
        _old_manifest = json.loads(_old_manifest_file.read_text())
        for _i, _s in enumerate(_old_manifest.get("skills", [])):
            _cf = contents_dir / f"idx_{_i}.txt"
            if _cf.exists():
                _c = _cf.read_text(errors="replace")
                if "Full content (truncated)" not in _c and len(_c) > 1000:
                    existing_full_cache[_s.get("name", "")] = _c
    except (OSError, json.JSONDecodeError, ValueError):
        pass  # corrupt old cache — proceed with fresh scan

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

        # Stub guard: if the deployed copy is a truncated stub but we have a
        # full copy in the previous run's cache, send the FULL content — never
        # let a stub overwrite the surviving full version.
        if "Full content (truncated)" in text or len(text) <= 1000:
            cached_full = existing_full_cache.get(name)
            if cached_full:
                text = cached_full

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

# ── Send to Moses inbox via PGMQ Agent Bus ────────────────────
BUS_URL="${CORTEX_BUS_URL:-${CORTEX_BUS_FALLBACK_URL:-${CORTEX_INBOX_URL:-}}}"
if [[ -n "$BUS_URL" ]]; then
  # Export vars for Python subprocess
  export STATE_DIR CORTEX_BUS_TOKEN CORTEX_BASIC_AUTH CORTEX_BUS_AUTH

  python3 << 'PYEOF'
import json, os, sys, urllib.request, urllib.error, base64, time
from pathlib import Path

state_dir = Path(os.environ["STATE_DIR"])
manifest_file = state_dir / "skills-manifest.json"
contents_dir = state_dir / "skill-contents"
bus_url = (os.environ.get("CORTEX_BUS_URL", "") or os.environ.get("CORTEX_BUS_FALLBACK_URL", "") or os.environ.get("CORTEX_INBOX_URL", "")).rstrip("/")

# Auth: localhost → Bearer, remote → Basic
host = bus_url.split("://")[-1].split("/")[0].split(":")[0]
if host in ("127.0.0.1", "localhost", "::1"):
    token = os.environ.get("CORTEX_BUS_TOKEN", "")
    auth_header = f"Bearer {token}" if token else ""
else:
    auth_creds = os.environ.get("CORTEX_BASIC_AUTH", "") or os.environ.get("CORTEX_BUS_AUTH", "")
    if auth_creds and ":" in auth_creds:
        encoded = base64.b64encode(auth_creds.encode()).decode()
        auth_header = f"Basic {encoded}"
    else:
        auth_header = ""

inbox_url = bus_url + "/api/pgmq/send"

if not manifest_file.exists():
    exit(0)

manifest = json.loads(manifest_file.read_text())
custom_total = manifest.get("custom_skills", 0)
if custom_total == 0:
    exit(0)

# Read skill contents from individual files (FULL content — no truncation)
contents = []
if contents_dir.is_dir():
    for i in range(len(manifest.get("skills", []))):
        cf = contents_dir / f"idx_{i}.txt"
        contents.append(cf.read_text() if cf.exists() else "")

hostname = os.uname().nodename
total_skills = manifest.get("total_skills", 0)
generated = manifest.get("generated", "")

# ── Build chunked messages with FULL skill content ──────────
# Bus limit is ~100KB per message. Skills average 3-10KB each, so a report
# with many skills must be split across multiple messages. Each message
# carries full (untruncated) content for a subset of skills. The subject
# keeps the "Skill Report:" prefix (downstream filters on it) with a
# part counter; the body keeps the "== Skill:" markers and the count
# lines so orch-skill-report-process.py can still parse every part.
MAX_BODY_BYTES = 90_000  # safety margin under the 100KB bus cap

header_lines = [
    f"━━━ Skill Report — {manifest.get('sender', hostname)} ━━━",
    f"Generated: {generated}",
    f"Total skills installed: {total_skills}",
    f"Custom skills (not upstream): {custom_total}",
    "",
]

def build_skill_block(i, s):
    name = s.get("name", "?")
    catg = s.get("category", "")
    tag = f" ({catg})" if catg else ""
    content = contents[i] if i < len(contents) else "(content unavailable)"
    return "\n".join([
        f"== Skill: {name}{tag} ==",
        f"Lines: {s.get('lines', 0)} | Age: {s.get('age_days', 0)}d",
        f"Description: {s.get('summary', '')}",
        "",
        "--- Full content ---",
        content,
        "--- End skill ---",
        "",
    ])

# Split skills into chunks that each fit under the size cap
chunks = []
current_chunk = []
current_size = 0
for i, s in enumerate(manifest.get("skills", [])):
    block = build_skill_block(i, s)
    block_size = len(block.encode("utf-8"))
    if current_chunk and current_size + block_size > MAX_BODY_BYTES:
        chunks.append(current_chunk)
        current_chunk = []
        current_size = 0
    current_chunk.append(block)
    current_size += block_size
if current_chunk:
    chunks.append(current_chunk)

# ── Send each chunk as its own inbox message ────────────────
headers = {"Content-Type": "application/json"}
if auth_header:
    headers["Authorization"] = auth_header

sent_any = False
for ci, chunk in enumerate(chunks):
    body_text = "\n".join(header_lines + chunk)
    if len(chunks) > 1:
        subject = f"Skill Report: {custom_total} custom skills (part {ci+1}/{len(chunks)})"
    else:
        subject = f"Skill Report: {custom_total} custom skills"

    payload = {
        "queue": "inbox_moses",
        "message": {
            "from": hostname,
            "subject": subject,
            "body": body_text,
            "topic": "reports",
            "priority": "normal",
        },
    }

    req = urllib.request.Request(
        inbox_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        sent_any = True
        print(f"Sent part {ci+1}/{len(chunks)} ({len(chunk)} skills) to Moses inbox", flush=True)
    except urllib.error.HTTPError as e:
        print(f"WARN: HTTP {e.code} sending skill report part {ci+1}: {e}", file=sys.stderr, flush=True)
    except urllib.error.URLError as e:
        print(f"WARN: Failed to send skill report part {ci+1}: {e}", file=sys.stderr, flush=True)
        exit(1)

if not sent_any and chunks:
    print(f"WARN: {custom_total} custom skills found but not sent (delivery failed)", file=sys.stderr, flush=True)
    exit(1)
PYEOF
fi
