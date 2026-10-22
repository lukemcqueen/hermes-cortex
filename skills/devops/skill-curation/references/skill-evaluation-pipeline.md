# Skill Evaluation Pipeline

## Overview

The skill evaluation pipeline collects, evaluates, and upstreams custom skills across the Hermes Cortex agent fleet. It runs on a cron schedule and produces a digest of findings.

## Pipeline Components

### Agent-side (every agent)
| Script | Schedule | Purpose |
|--------|----------|---------|
| `collect-agent-skills.sh` | Every 6h | Scans `~/.hermes/skills/` and `~/.hermes-cortex/skills/` for SKILL.md files not in `runtime/skills/`. Writes manifest to `~/.hermes-cortex/state/skills-manifest.json`. |
| `send-skill-report.py` | Every 6h (+30m) | Reads manifest and posts to Moses inbox via JSON API. Silent exit if no custom skills. |

### Orchestrator-side (Moses / evaluator)
| Script | Schedule | Purpose |
|--------|----------|---------|
| `process-skill-reports.py` | Every 6h | Reads inbox `reports` topic for skill-report messages. Compiles digest. Accepts `--all`, `--mark-read`. |

### File locations
All scripts: `~/hermes-cortex/ops/scripts/manage/`
State dir: `~/.hermes-cortex/state/`
Manifest: `skills-manifest.json`
Last-processed marker: `last-skill-report-processed.txt`
Skill contents: `skill-contents/idx_{N}.txt`

## Known Issues & Pitfalls

### 401 on process-skill-reports.py
- **Symptom:** `WARN: Could not fetch inbox: HTTP Error 401: Unauthorized`
- **Cause:** `CORTEX_INBOX_AUTH` not set in agent's `.env` (at `~/hermes-cortex/.env` or `~/.hermes/hermes-inbox.conf`)
- **Fix:** Add `CORTEX_INBOX_AUTH=username:password` to `.env`. The `CORTEX_INBOX_URL` alone is insufficient.
- **Who sets it:** The orchestrator (Moses) typically has auth. Leaf agents may not — they rely on the orchestrator to collect.

### Missing YAML descriptions
- Many custom skills have `(no description)` because their YAML frontmatter uses multi-line `description: |` or `description: >` syntax that the Python extraction logic doesn't handle.
- **Fix when authoring:** Use single-line `description: "..."` or fix the extraction regex in collect-agent-skills.sh to handle folded/block scalars.

### .claude/ path references
- Several marketing skills reference `.claude/product-marketing-context.md`. This is Claude-specific and should be generalized to an env-var-based `CONTEXT_FILE` pattern before upstreaming.

### Duplicate entries in manifest
- Skills that exist under two different category paths (e.g., `software-development/` and `skills/software-development/`) appear as separate custom entries.
- De-duplication happens at the file level, not the skill level. A skill name appearing N times = N paths scanned.

### State marker missing on first deployment
- **Symptom:** `process-skill-reports.py` shows ALL historical reports (15+ agents) every run, even though they were already processed.
- **Cause:** `~/.hermes-cortex/state/last-skill-report-processed.txt` doesn't exist. The dedup guard that filters `msg_id > last_processed` has no reference point.
- **Fix:** After confirming no new content was missed, run:
  ```bash
  python3 ~/hermes-cortex/ops/scripts/manage/process-skill-reports.py --mark-read
  ```
  This archives the messages and writes the marker file. Future runs will only show truly new reports.

### PGMQ visibility timeout gaps
- **Symptom:** `process-skill-reports.py` returns nothing (`[SILENT]`), but you know agents should have sent reports.
- **Cause:** PGMQ read consumes the message with a visibility timeout (VT). If a prior call read messages but never archived them (no `--mark-read`), they're hidden by VT. After VT expiry they reappear — but may be misattributed as "new" on re-read.
- **Fix:** Cross-check by probing the queue directly (see "Manual PGMQ Bus Probing" below).

### Learning Reports vs Skill Reports
- The bus carries two distinct message types:
  - **Skill Report** (subject: `Skill Report: N custom skills`) — full inventory of installed custom skills. Handled by `process-skill-reports.py`.
  - **Learning Report** (subject: `Learning Report: N skills, M lessons`) — delta of skills changed / lessons learned. Handled by `orch-skill-lifecycle` Phase 1 directly.
- Don't confuse them. `process-skill-reports.py` only catches Skill Reports. If you see Learning Reports but no Skill Reports, that's expected.

## Evaluation Criteria for Upstreaming

When evaluating a custom skill for upstreaming into `runtime/skills/`:

1. **Well-structured YAML frontmatter**: Has proper `name:`, `description:`, `version:`, `license:` fields.
2. **General-purpose**: Not specific to one agent, one deployment, or one infrastructure.
3. **MIT-licensed**: The hermes-cortex repo is MIT. Skills must be MIT-compatible.
4. **No private paths**: No references to private domains, internal IPs, or agent-specific name patterns.
5. **Self-contained**: No reliance on external APIs, private registries, or uninstalled packages.
6. **No deprecation redirects**: Deprecated skills should be removed, not kept as redirect stubs.

## Grading Scale

| Score | Meaning | Action |
|-------|---------|--------|
| 5/5 | Mature, versioned, stack-agnostic | Immediate upstream |
| 4/5 | Well-structured, minor path issues | Upstream after trivial fixes |
| 3/5 | Useful but thin or domain-specific | Consider upstream or keep custom |
| 2/5 | Infrastructure-coupled or niche | Keep custom |
| 1/5 | Deprecated or stale | Delete |

## Manual PGMQ Bus Probing

When `process-skill-reports.py` returns unexpected results (empty, stale, or no new reports), probe the PGMQ queue directly:

```python
# Read pending messages from inbox_moses to check for Skill Reports
python3 -c "
import json, os
from urllib.request import Request, urlopen
from pathlib import Path

# Resolve token
token = os.environ.get('CORTEX_BUS_TOKEN', '')
if not token:
    for line in open(Path.home() / 'hermes-cortex' / '.env').read().splitlines():
        if line.startswith('CORTEX_BUS_TOKEN='):
            token = line.split('=', 1)[1].strip().strip(\"'\")
            break
bus = (os.environ.get('CORTEX_BUS_URL') or 'http://127.0.0.1:8903').rstrip('/')

for i in range(5):
    p = json.dumps({'queue': 'inbox_moses', 'vt': 60, 'limit': 3}).encode()
    r = urlopen(Request(f'{bus}/api/pgmq/read',
       data=p,
       headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
       method='POST'), timeout=10)
    d = json.loads(r.read().decode())
    if not isinstance(d, dict) or not d.get('msg_id'):
        print(f'No more messages after batch {i}')
        break
    b = d['body']
    if isinstance(b, str):
        try: b = json.loads(b)
        except: pass
    s = b.get('subject','')[:100]
    f = b.get('from','?')
    body_preview = str(b.get('body',''))[:150].replace(chr(10),' | ')
    print(f'[{i}] msg_id={d[\"msg_id\"][:20]} from={f} subject={s}')
    print(f'    preview: {body_preview}')
"
```

Key things to check when probing:
- **Subject line** — starts with "Skill Report:" (skill inventory) vs "Learning Report:" (lesson delta)
- **From agent** — which agent sent it, to correlate with expected report cadence
- **Body format** — Skill Reports start with `━━━ Skill Report — {hostname} ━━━`, Learning Reports with `━━━ Learning Report`

## Upstream Inventory Comparison

When an agent reports 230+ "custom" skills but you need to know which are truly novel:

```bash
# Collect all upstream skill names (handles maxdepth 3 category nesting)
cd ~/hermes-cortex
find skills -maxdepth 3 -name SKILL.md | sed 's|.*/||; s|/SKILL\\.md$||' | sort -u > /tmp/upstream-skills.txt

# Collect the agent's reported custom skills from the bus report body
# (parse the `== Skill: name (category) ==` lines)
grep '^== Skill:' /tmp/skill-report-body.txt | sed 's/== Skill: //; s/ *(.*//' > /tmp/reported-skills.txt

# Novel skills = reported but NOT in upstream
comm -23 /tmp/reported-skills.txt /tmp/upstream-skills.txt
```

Most agents (LAM2, cisnet03, luke-server) report the standard fleet skill set. In practice, 0-7 skills out of 235 may be truly novel — and those are typically category-level wraps or agent-specific tools (computer-use, yuanbao, etc.) that shouldn't be upstreamed.

## Quick Reference Commands

```bash
# Collect skills manifest
bash ~/hermes-cortex/ops/scripts/manage/collect-agent-skills.sh

# Send report
python3 ~/hermes-cortex/ops/scripts/manage/send-skill-report.py

# Process reports (orchestrator-side)
python3 ~/hermes-cortex/ops/scripts/manage/process-skill-reports.py --mark-read

# Check which skills are truly custom vs already upstreamed
cd ~/hermes-cortex
python3 -c "
import json
from pathlib import Path
m = json.loads(Path('~/.hermes-cortex/state/skills-manifest.json').expanduser().read_text())
r = {p.parent.name for p in Path('runtime/skills').rglob('SKILL.md')}
for s in m['skills']:
    if s['name'] not in r:
        print(f'CUSTOM: {s[\"name\"]} ({s.get(\"category\",\"\")})')
"
```
