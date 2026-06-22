# Cron Job Recipes for Hermes Agent

> **Version 1.3.0** — Published 2026-06-15
> A collection of reusable cron job prompts and scripts for Hermes Agent automation.

---

This cookbook contains production-tested cron job recipes you can copy, customize, and deploy with your Hermes Agent. Each recipe includes the full prompt, schedule recommendation, required toolsets, and setup instructions.

---

## How to Use

```bash
# Create a cron job with the Hermes CLI using hermes agent prompt
hermes cron create \
  --name "my-job-name" \
  --schedule "0 1 * * *" \
  --prompt "Paste the recipe prompt here"
```

For no_agent script jobs, save the script to `~/.hermes/scripts/` and create:
```bash
hermes cron create \
  --name "my-script-job" \
  --schedule "every 10m" \
  --script "my-script.py" \
  --no-agent
```

---

## 💾 Memory Budget Monitor

Alerts you when MEMORY.md or USER.md approach the 2,200/1,375 character limits. Silent when healthy, warns at ≥85%, alerts at ≥95%.

**Schedule:** `0 5 * * *` (5am daily)
**Type:** no_agent (script)

### Recipe

```bash
# Create the cron job:
hermes cron create \
  --name "memory-budget-check" \
  --schedule "0 5 * * *" \
  --script "check-memory-budget.sh" \
  --no-agent
```

The script outputs:
- `🟢 MEMORY.md: 42% (920/2200) — OK` when healthy → silent (no output)
- `🟡 MEMORY.md: 87% (1914/2200) — WARNING` at ≥85%
- `🔴 MEMORY.md: 96% (2112/2200) — CRITICAL` at ≥95%

On warning or critical, it suggests running the pointer pattern compression or `bootstrap-brain.sh`.

### Manual Check

```bash
bash ~/.hermes/scripts/check-memory-budget.sh --report
```

---

## 📖 Daily Bible Reading

Delivers a daily book-of-the-Bible summary with 3 thoughtful insights, saves to a searchable personal brain, and tracks progress through all 66 books.

**Schedule:** `0 1 * * *` (1am daily)
**Type:** LLM-driven

### Recipe

```
## Daily Bible Reading — 1 Book, Summary, Insights

Today you will read ONE book of the Bible and deliver a concise summary with 3 assessments.

### Step 1: Find Today's Book

Create a tracker at `~/.hermes/bible-tracker.json` with a `schedule` array of all 66 books
and a `read_index`. The value at `schedule[read_index]` is today's book.

If `read_index >= 66`, reset to 0 and restart the cycle.

### Step 2: Read the Book

Use `web_extract` on `https://bible-api.com/{book_name}+{chapter_number}?translation=web`
to fetch each chapter (World English Bible — public domain).

- **Short books (1–5 chapters):** fetch ALL chapters
- **Medium books (6–15 chapters):** fetch first 3, last 2, and famous chapters
- **Long books (16+ chapters):** fetch first 2, last 1, and famous chapters (max 8)
- **Psalms (150 chapters):** read Psalms 1, 23, 51, 103, 139, 150
- **Proverbs (31 chapters):** read Proverbs 1–3, 10, 31
- **Isaiah (66 chapters):** read chapters 1, 6, 9, 40, 53, 55, 65

### Step 3: Write the Summary + 3 Ideas

Compose a message with:

1. **📖 Book title**
2. **Concise summary** (3–5 sentences capturing the core message/arc/themes)
3. **3 ideas or assessments** — thoughtful, applicable insights connected to leadership,
   wisdom, resilience, or guidance (not just recaps)
4. **Top insight** — the single most relevant takeaway for the agent's character/persona

### Step 4: Save to a Personal Brain Directory (Optional)

If you have a personal agent brain directory:

1. Save the full summary to `~/brain/{agent-name}/bible/{book-slug}.md`
2. Update a running INDEX.md table
3. Git commit + push
4. Re-index gbrain (if using it)

### Step 5: Update State

**Update `~/.hermes/bible-tracker.json`:**
- Increment `read_index` by 1 (wrap to 0 if ≥ 66)
- Add today's book name to completed array

### Notes
- World English Bible (WEB) translation is public domain
- Bible book names must match bible-api.com conventions
  (e.g. "Song of Solomon", not "Song of Songs")
- Book sampler reduces API calls for long books
```

### Setup

```bash
# Create the tracker
echo '{"schedule": ["Genesis","Exodus","Leviticus","Numbers","Deuteronomy","Joshua","Judges","Ruth","1 Samuel","2 Samuel","1 Kings","2 Kings","1 Chronicles","2 Chronicles","Ezra","Nehemiah","Esther","Job","Psalms","Proverbs","Ecclesiastes","Song of Solomon","Isaiah","Jeremiah","Lamentations","Ezekiel","Daniel","Hosea","Joel","Amos","Obadiah","Jonah","Micah","Nahum","Habakkuk","Zephaniah","Haggai","Zechariah","Malachi","Matthew","Mark","Luke","John","Acts","Romans","1 Corinthians","2 Corinthians","Galatians","Ephesians","Philippians","Colossians","1 Thessalonians","2 Thessalonians","1 Timothy","2 Timothy","Titus","Philemon","Hebrews","James","1 Peter","2 Peter","1 John","2 John","3 John","Jude","Revelation"],"read_index":0,"completed":[]}' > ~/.hermes/bible-tracker.json

# Create the brain directory (optional)
mkdir -p ~/brain/agent-name/bible
```

---

## 🚨 System Alert Watchdog

Monitors memory, swap, and disk usage. Sends Telegram alerts when thresholds are exceeded. Runs silently when everything is healthy.

**Schedule:** `every 10m`
**Type:** no_agent script

### Script (`~/.hermes/scripts/system-alert.py`)

```python
#!/usr/bin/env python3
"""System resource alert watchdog.

Checks: memory >85%, swap >70%, disk >90%.
Sends alerts to Telegram via Hermes delivery system.
Silent when all clear — only output if there's a problem.
"""
import json, os, subprocess, sys
from pathlib import Path

HOME = Path.home()
THRESHOLDS = {"memory_pct": 85, "swap_pct": 70, "disk_pct": 90}

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return r.stdout.strip()

def check_memory():
    out = run("memory_pressure 2>/dev/null | head -5")
    for line in out.split("\n"):
        if "pages free" in line:
            total = 4194304  # 16 GB in 4KB pages — adjust for your system
            free = int(line.split(":")[-1].strip().split(".")[0])
            used_pct = round((1 - free / total) * 100, 1)
            return used_pct
    return 0

def check_swap():
    out = run("sysctl vm.swapusage 2>/dev/null")
    for part in out.split(","):
        part = part.strip()
        if part.startswith("used"):
            pct = part.split("=")[-1].strip().replace("M", "")
            return float(pct)
    return 0

def check_disk():
    out = run("df -h / | tail -1 | awk '{print $5}' | tr -d '%'")
    return int(out) if out else 0

def main():
    mem = check_memory()
    swap = check_swap()
    disk = check_disk()
    issues = []
    if mem > THRESHOLDS["memory_pct"]:
        issues.append(f"🔴 Memory: {mem}%")
    if swap > THRESHOLDS["swap_pct"]:
        issues.append(f"🔴 Swap: {swap}%")
    if disk > THRESHOLDS["disk_pct"]:
        issues.append(f"🔴 Disk: {disk}%")
    if issues:
        print("🚨 System Alert:")
        for i in issues:
            print(f"  {i}")
        sys.exit(0)
    # Silent — no output means all clear

if __name__ == "__main__":
    main()
```

### Setup

```bash
# Save the script
chmod +x ~/.hermes/scripts/system-alert.py

# Create the cron job (adjust thresholds in the script for your system)
hermes cron create \
  --name "system-alert-watchdog" \
  --schedule "every 10m" \
  --script "system-alert.py" \
  --no-agent \
  --deliver "origin"
```

---

## 🔧 Service Recovery Watchdog

Auto-restarts critical services (nginx, Docker containers) if they go down. Checks every 5 minutes.

**Schedule:** `every 5m`
**Type:** no_agent script

### Script (`~/.hermes/scripts/service-recovery.py`)

```python
#!/usr/bin/env python3
"""Service recovery watchdog. Restarts nginx and Docker containers if down."""
import subprocess, sys

def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except:
        return -1, "", "timeout"

def check_nginx():
    rc, _, _ = run("pgrep nginx")
    if rc != 0:
        print("⚠️ nginx is down — attempting restart...")
        rc2, out, err = run("nginx 2>&1")
        if rc2 == 0:
            print("✅ nginx restarted successfully")
        else:
            print(f"❌ nginx restart failed: {err}")
        return rc2 == 0
    return True

def check_containers():
    rc, out, _ = run("docker ps --filter name=langfuse --format '{{.Names}}'")
    if rc != 0:
        print("⚠️ Docker not running — attempting restart...")
        rc2, _, _ = run("open -a Docker && sleep 30 && docker compose -f ~/docker-compose.yml up -d")
        if rc2 == 0:
            print("✅ Docker restarted and containers up")
        return False
    lines = [l for l in out.split("\n") if l.strip()]
    if not lines:
        print("⚠️ Langfuse containers not running — restarting...")
        run("docker compose -f ~/docker-compose.langfuse.yml up -d")
        print("✅ Langfuse containers restarted")
        return True
    return True

def main():
    nginx_ok = check_nginx()
    containers_ok = check_containers()
    if not nginx_ok or not containers_ok:
        print("Recovery actions completed")
    # Silent if all healthy

if __name__ == "__main__":
    main()
```

### Setup

```bash
# Create the cron job
hermes cron create \
  --name "service-recovery" \
  --schedule "every 5m" \
  --script "service-recovery.py" \
  --no-agent \
  --deliver "origin"
```

---

## 💖 System Heartbeat

Checks system health every 30 minutes and alerts via Telegram if anything is DOWN or DEGRADED. Silent when all healthy.

**Schedule:** `*/30 * * * *`
**Type:** LLM-driven + companion script
**Toolsets:** `terminal`

### Companion Script (`~/.hermes/scripts/heartbeat.py`)

```python
#!/usr/bin/env python3
"""System heartbeat — reports service health status.
Output is read by the LLM cron job for alerting decisions."""
import json, os, subprocess, sys
from datetime import datetime

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return r.returncode, r.stdout.strip()

def check_uptime():
    rc, out = run("uptime | awk -F'up ' '{print $2}' | awk -F',' '{print $1}'")
    return out if rc == 0 else "unknown"

def check_memory():
    rc, out = run("memory_pressure 2>/dev/null | grep 'pages free'")
    if rc == 0:
        free = int(out.split(":")[-1].strip().split(".")[0])
        total = 4194304
        pct = round((1 - free / total) * 100, 1)
        return pct
    return 0

def check_disk():
    rc, out = run("df -h / | tail -1 | awk '{print $5}' | tr -d '%'")
    return int(out) if rc == 0 else 0

def check_docker():
    rc, out = run("docker ps --format '{{.Names}}'")
    if rc != 0: return [], "DOWN"
    names = [l for l in out.split("\n") if l.strip()]
    rc2, out2 = run("docker ps --filter 'status=running' --format '{{.Names}}'")
    running = [l for l in out2.split("\n") if l.strip()] if rc2 == 0 else []
    return names, running

def check_nginx():
    rc, _ = run("pgrep nginx")
    return "OK" if rc == 0 else "DOWN"

def check_dashboard():
    rc, out = run("curl -s -o /dev/null -w '%{http_code}' http://localhost:8901/health 2>/dev/null")
    return "OK" if out == "200" else f"DEGRADED ({out})"

def main():
    services = {
        "nginx": check_nginx(),
        "dashboard": check_dashboard(),
    }
    docker_names, docker_running = check_docker()
    if docker_names:
        services["docker_containers"] = f"{len(docker_running)}/{len(docker_names)} running"
        if len(docker_running) < len(docker_names):
            services["docker_status"] = "DEGRADED"
        else:
            services["docker_status"] = "OK"
    mem = check_memory()
    disk = check_disk()
    report = {
        "timestamp": datetime.now().isoformat(),
        "uptime": check_uptime(),
        "memory_pct": mem,
        "disk_pct": disk,
        "services": services,
    }
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
```

### LLM Prompt Recipe

```
You are an AI assistant running system heartbeat checks.

Run the heartbeat script: `python3 ~/.hermes/scripts/heartbeat.py --report`

Read its output. If the output is empty (all healthy), stay completely silent —
do nothing, send nothing.

If the output contains any ❌ (DOWN), 🔴 (ERROR), or ⚠️ (DEGRADED) status items:
1. Compose a concise alert message summarizing what's wrong
2. Send it as your final response (system auto-delivers)
3. Keep the message clear and actionable

If only DEGRADED items (no DOWN/ERROR), send a single heads-up.
```

### Setup

```bash
# Create the cron job
hermes cron create \
  --name "system-heartbeat" \
  --schedule "*/30 * * * *" \
  --prompt "Paste the LLM prompt above" \
  --deliver "origin"
```

---

## 🧠 Memory Pruning

Daily LLM-driven review of agent memory. Reads MEMORY.md, consolidates redundant entries, removes stale facts, and keeps under the character limit.

**Schedule:** `0 4 * * *` (4am daily)
**Type:** LLM-driven
**Toolsets:** `terminal`

### Recipe

```
You are an AI assistant managing your own memory.

Run the memory pruning cycle using FILE I/O.

## Steps

1. **Run mechanical compression first:** Execute `python3 ~/.hermes/scripts/memory-compress.py`
   to consolidate exact duplicates and trim verbose entries.

2. **Read current memory:** Execute `cat ~/.hermes/memories/MEMORY.md` to read the
   compressed output. Parse the §-separated entries.

3. **Review each entry critically:**
   - Is it still accurate and relevant?
   - Is it superseded by a newer entry? (if so, mark for removal)
   - Does it reference an old version of something that's changed? (if so, update it)

4. **Apply changes using write_file or patch:**
   - Remove stale entries by writing the file back without them
   - Update outdated info by writing corrected versions
   - Keep redundant entries if they add unique info

5. **Report what you did** — which entries were kept, updated, or removed, and why.

## Guidelines

- Be ruthless with truly stale entries (completed tasks, superseded info, noise)
- Be conservative with entries you're unsure about — better to keep than lose
- Target ~1,800 chars of the 2,200 limit to leave room for growth
- Use write_file to rewrite MEMORY.md — it handles the full file atomically
```

### Setup

```bash
hermes cron create \
  --name "memory-pruning" \
  --schedule "0 4 * * *" \
  --prompt "Paste the recipe above" \
  --deliver "origin"
```

---

## 🗜️ Memory Compression (Mechanical Fallback)

A no_agent safety net that mechanically trims over-long entries, removes exact duplicates, and stays under the 2,200 character limit.

**Schedule:** `0 5 * * 0` (Sunday 5am)
**Type:** no_agent script

### Script (`~/.hermes/scripts/memory-compress.py`)

```python
#!/usr/bin/env python3
"""memory-compress.py — Compress Hermes memory while preserving meaning.

Reads MEMORY.md, compacts over-long entries, removes duplicates,
and keeps the total under the 2,200 char limit. Designed for
no_agent cron usage.

Usage:
    python3 ~/.hermes/scripts/memory-compress.py [--dry-run]

Exit: 0 = no changes, 1 = changes made
"""
import os, sys

MEMORY_FILE = os.path.expanduser("~/.hermes/memories/MEMORY.md")
LOCK_FILE = MEMORY_FILE + ".lock"
MAX_CHARS = 2200
TRIM_CHARS = 300

def parse_entries(text):
    return [e.strip() for e in text.split("§") if e.strip()]

def format_entries(entries):
    return "\n§\n".join(entries) + "\n"

def trim_to_essential(entry, max_chars=TRIM_CHARS):
    if len(entry) <= max_chars:
        return entry, False
    lines = entry.split("\n")
    first = lines[0].strip()
    trimmed = [first]
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(p) for p in ["-", "*", "1.", "2.", "3.", "Key", "Note"]):
            trimmed.append(line)
        elif len(" ".join(trimmed + [line])) < max_chars * 0.8:
            trimmed.append(line)
    result = "\n".join(trimmed)
    if len(result) > max_chars:
        result = result[:max_chars - 3] + "..."
    return result, True

def remove_duplicates(entries):
    seen = set()
    result = []
    changes = False
    for e in entries:
        fingerprint = " ".join(e.lower().split())
        if fingerprint in seen:
            changes = True
            continue
        dup = False
        for s in seen:
            if fingerprint in s or s in fingerprint:
                if abs(len(fingerprint) - len(s)) < 30:
                    dup = True
                    changes = True
                    break
        if not dup:
            seen.add(fingerprint)
            result.append(e)
        else:
            changes = True
    return result, changes

def main():
    dry_run = "--dry-run" in sys.argv
    if not os.path.exists(MEMORY_FILE):
        print("MEMORY.md not found.")
        return 0
    with open(MEMORY_FILE) as f:
        original = f.read()
    entries = parse_entries(original)
    if len(entries) <= 3 and len(original) <= MAX_CHARS:
        print("Already compact")
        return 0
    changes = False
    entries, dup_changes = remove_duplicates(entries)
    changes = changes or dup_changes
    trimmed_count = 0
    for i, e in enumerate(entries):
        trimmed, did_trim = trim_to_essential(e)
        if did_trim:
            entries[i] = trimmed
            trimmed_count += 1
            changes = True
    new_content = format_entries(entries)
    if len(new_content) > MAX_CHARS:
        overage = len(new_content) - MAX_CHARS
        per_entry = overage // max(len(entries), 1) + 10
        for i, e in enumerate(entries):
            if len(e) > 100:
                shorten_by = min(per_entry, len(e) - 50)
                if shorten_by > 0:
                    entries[i] = e[:-shorten_by].rstrip() + "..."
                    changes = True
        new_content = format_entries(entries)
    if changes and not dry_run:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        with open(MEMORY_FILE, "w") as f:
            f.write(new_content)
    saved = len(original) - len(new_content)
    print(f"Compression: {len(entries)} entries, {len(original)}→{len(new_content)} chars ({'-' if saved > 0 else '+'}{abs(saved)})")
    return 1 if changes else 0

if __name__ == "__main__":
    sys.exit(main())
```

### Setup

```bash
hermes cron create \
  --name "memory-compress" \
  --schedule "0 5 * * 0" \
  --script "memory-compress.py" \
  --no-agent
```

---

## 💡 Weekly Opportunity Scan (with Auto-Fix)

Scan-fix-verify-report cycle — checks git, Docker, permissions, disk, and cron health,
then automatically fixes known recurring issues, verifies each fix, and reports
what was resolved and what still needs attention.

**Schedule:** `0 8 * * 1` (Monday 8am)
**Type:** LLM-driven + companion no_agent script
**Toolsets:** `terminal`, `web`

### Recipe

```
You are an AI assistant running a weekly opportunity scan with auto-fix and verification.

## Phase 1: Scan

Check repos, Docker containers, system files, and cron jobs for issues:
- Git status: is the repo behind origin/main? Stale branches? Unmerged PRs?
- Docker health: any containers in "unhealthy" or "restarting" state?
- File permissions: world-readable cron outputs (should be 600)?
- Disk usage: large caches (>100MB) that should be cleaned?
- Cron job errors: check for last_status: error in the cron job list.

Also scan ~/brain/*/ and gbrain for incomplete tasks, stale branches,
or new ideas that need attention.

## Phase 2: Auto-Fix

After identifying issues, attempt to fix them:

**Git fixes:** `git pull --rebase --autostash` if behind origin/main.
Delete local branches whose remote tracking refs are gone (`git branch -vv | grep ': gone]'`).
Merge ready PRs with `gh pr merge --squash`.

**Docker fixes:** `docker restart <name>` for unhealthy/restarting containers.

**Permission fixes:** `chmod 600` on world-readable scorer summaries.
`chmod 644` on executable pid files.

**Companion script:** Run `python3 ~/.hermes/scripts/orch-weekly-auto-fix.py --verbose`
as a safety net that handles additional known patterns.

## Phase 3: Verify

After each fix, verify it actually succeeded:

**Git verify:** Re-check behind count is now 0. Run `git status --short`
and check no conflict markers (`UU`, `AA`, `DD`) exist. For deleted branches,
confirm they're absent from `git branch`.

**Docker verify:** Re-run `docker ps` — the container should show "Up" or
"healthy", not "unhealthy" or "restarting".

**Permission verify:** `stat -f %p <file>` should show the target mode (600/644).

**Script verify:** The companion script outputs `verify_results` with
PASS/FAIL/WARN per check — read and incorporate its results.

## Phase 4: Report

Output max 3 items under 200 chars each. For each, say whether it was
FIXED (fix + verification passed), FAILED (fix or verification failed),
or WARN (partial success).

If everything was fixed and verified: "✅ All fixed & verified: [items]"
If nothing needed fixing: exit silently (no output).
```

### Setup

```bash
# 1. Deploy companion script
cp hermes-cortex/scripts/orch-weekly-auto-fix.py ~/.hermes/scripts/orch-weekly-auto-fix.py

# 2. Create the cron
hermes cron create \
  --name "weekly-scan-opportunities" \
  --schedule "0 8 * * 1" \
  --prompt "Paste the recipe above" \
  --deliver "origin"
```

---

## 🔄 GBrain Conversation Export

Exports recent agent conversations as markdown notes into brain directories for long-term knowledge retention.

**Schedule:** `0 */6 * * *` (every 6 hours)
**Type:** LLM-driven
**Toolsets:** `terminal`, `session_search`

### Recipe

```
You are a conversation archivist. Export recent agent sessions as markdown
notes into brain directories so they become searchable.

## Rules
- Only export sessions from the last 6 hours
- Save to ~/brain/{user}/conversations/ based on conversation context
- DO NOT re-export sessions already saved — check existing filenames
- Keep summaries concise: key Q&A, decisions, action items, important facts
- Frontmatter each file with: session_id, date, user, tags
- AFTER writing each file, git add + git commit it in the source repo

## Steps
1. Call session_search() to browse recent sessions from the past ~6 hours.
2. For each session, scroll through to understand the content.
3. Determine who the user is from conversation context.
4. Check existing conversation files — don't duplicate.
5. Write a markdown note with format YYYY-MM-DD-short-topic.md.
6. After writing, cd into the source git repo and commit.
7. Report what you exported.

## Example content:
---
session_id: "20260603_041524_c1e7908f"
date: 2026-06-03
user: user-name
tags: [topic1, topic2]
---

# Conversation Summary: Topic

Key decisions, action items, and important facts from the session.
```

### Setup

```bash
hermes cron create \
  --name "gbrain-conversation-export" \
  --schedule "0 */6 * * *" \
  --prompt "Paste the recipe above" \
  --deliver "local" \
  --workdir "$HOME"
```

---

## 🌅 Daily Morning Briefing

Comprehensive morning briefing covering Korean peninsula news, world Christianity, Bible verses, and system health.

**Schedule:** `30 6 * * *` (6:30am daily)
**Type:** LLM-driven
**Toolsets:** `web`, `terminal`, `session_search`

### Recipe (Sanitized)

```
You are an AI assistant running a daily morning briefing at 6:30am.
Be calm, thorough, and truthful.

Your final response will be auto-delivered to the user.

## Your Task — Comprehensive Morning Briefing

### Part 1: Local/Regional Deep Research (customize for your region)

Research your region or interest area across these domains. For each,
distill the top 3 things the user should care about today:

1. **Politics** — leadership changes, diplomacy, tensions, policy shifts
2. **Religion/Spirituality** — religious trends, church developments, movements
3. **Music** — cultural outputs, notable releases, underground scenes
4. **Business** — trade, tech, economy, local industry news
5. **World Perspective** — how the region is seen globally

**Source diversity is critical.** Search from multiple perspectives:
local-language sources, US/UK outlets, and relevant international perspectives.

Make ~8-15 web searches to cover the breadth.

### Part 2: World Christianity & Faith News (Optional)

Research worldwide:
1. **Christianity & Evangelism** — major developments, revivals, missions
2. **Persecution** — where Christians are being persecuted, new restrictions
3. **Believers Growth/Decline** — statistics and trends by region

### Part 3: Bible Verses

Find and quote exactly 3 Bible verses:
- 1 from the Old Testament (not from Psalms)
- 1 from Psalms specifically
- 1 from the New Testament
Include book, chapter, verse. Quote the ESV text accurately.

### Part 4: Save to Brain (if configured)

Save a dated copy of the briefing to your brain directory archive
before delivering the final response.

### Guidelines
- Be efficient — ~15-20 web searches total, batched logically
- Be truthful — never fabricate
- Be concise within depth — top 3 per category
- Skip filler — if a topic has nothing notable, skip it
- Bible verses must be factually accurate — no made-up content
```

---

## 🗄️ GBrain Nightly Maintenance

Runs the gbrain maintenance cycle: syncs all sources, then runs the dream cycle for knowledge consolidation.

**Schedule:** `0 3 * * *` (3am daily)
**Type:** LLM-driven
**Toolsets:** `terminal`

### Recipe

```
Run the nightly gbrain maintenance cycle:

1. First sync all sources:
   `cd ~ && export PATH="$HOME/.bun/bin:$PATH" && gbrain sync --all --parallel 4 --no-pull --no-embed --no-extract`

2. Then run the dream cycle:
   `cd ~ && export PATH="$HOME/.bun/bin:$PATH" && gbrain dream`

3. Report back a brief summary of what was synced and any dream cycle findings.
```

### Setup

```bash
hermes cron create \
  --name "gbrain-nightly-dream" \
  --schedule "0 3 * * *" \
  --prompt "Paste the recipe above" \
  --deliver "origin" \
  --workdir "$HOME"
```

---

## 🔄 Offline Content Auto-Update (no_agent)

Check for updates to downloaded Bible, hymns, and reference content.
Runs as a no_agent script job — zero token cost, only produces output
when something actually changes.

**Schedule:** Weekly on Sunday at 09:00

**Script:** Save `hermes-cortex/src/offline/auto-update.sh` to `~/.hermes/scripts/auto-update.sh`

**Setup:**

```bash
cp ~/hermes-cortex/src/offline/auto-update.sh ~/.hermes/scripts/auto-update.sh
chmod +x ~/.hermes/scripts/auto-update.sh
```

**Cron creation:**

```bash
hermes cron create \
  --name "offline-content-update" \
  --schedule "0 9 * * 0" \
  --script "auto-update.sh" \
  --no-agent \
  --deliver "origin"
```

**Behavior:**
- Checks internet connectivity first — if offline, exits silently
- **Bible:** Parses any `.txt` files that lack `.json` (completing partial downloads)
- **Hymns:** Checks Open Hymnal Project PDF/ABC/XML for size changes via HEAD request — downloads only if different
- **ZIM:** Lists current files (actual download skipped — multi-GB files are user-initiated)
- Only produces output when something was actually updated
- Logs changes to `~/offline/auto-update.log`

---

## 📊 Layout at a Glance

| Time (24h) | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---|---|---|---|---|---|---|
| **01:00** | 📖 Bible | 📖 Bible | 📖 Bible | 📖 Bible | 📖 Bible | 📖 Bible | 📖 Bible |
| **02:00** | 🔄 Brew | 🔄 Brew | 🔄 Brew | 🔄 Brew | 🔄 Brew | 🔄 Brew | 🔄 Brew |
| **02:30** | 🔄 Hermes | 🔄 Hermes | 🔄 Hermes | 🔄 Hermes | 🔄 Hermes | 🔄 Hermes | 🔄 Hermes |
| **03:00** | 🧠 gbrain | 🧠 gbrain | 🧠 gbrain | 🧠 gbrain | 🧠 gbrain | 🧠 gbrain | 🧠 gbrain |
| **04:00** | 🧠 Memory | 🧠 Memory | 🧠 Memory | 🧠 Memory | 🧠 Memory | 🧠 Memory | 🧠 Memory |
| **05:00** | | | | | | | 🗜️ Compress |
| **06:30** | 🌅 Brief | 🌅 Brief | 🌅 Brief | 🌅 Brief | 🌅 Brief | 🌅 Brief | 🌅 Brief |
| **07:00** | | | | | | | 📊 Analysis |
|| **08:00** | 💡 Weekly | | | | | | |
|| **Ongoing** | 🚨 Alert (10m), 🔧 Recovery (5m), 💖 Heartbeat (30m), 🔄 Export (6h), 📬 Inbox Processor (10m) |

---

## 📨 Moses Inbox Remediation Processor

Detects agent-inbox messages from peer agents flagged as needing a fix (by keyword
match: "error", "broken", "help", etc.) and auto-remediates within ~10 minutes.

**Schedule:** `every 10m`
**Type:** LLM-driven + companion no_agent script
**Toolsets:** `terminal`, `file`, `web`

### Recipe

```
You are Moses. This is your inbox remediation processor.

## Step 1: Check for pending remediation markers

Run the companion script: `~/.hermes/scripts/orch-moses-inbox-remediate.sh`
If output is `[]`, respond with [SILENT] — nothing needs remediation.

## Step 2: Process each pending item

For each item (sender, subject, body, marker_file), determine what fix
is needed and apply it using terminal/web tools.

## Step 3: Fix it

Apply the fix. Also run `python3 ~/.hermes/scripts/orch-weekly-auto-fix.py --verbose`
as a safety net for mechanical patterns.

## Step 4: Mark remediation as done

Run:
  mkdir -p ~/.hermes/state/remediate/done
  mv <marker_file> ~/.hermes/state/remediate/done/
  cd ~/hermes-cortex-private && git add -A && git commit -m "remediation: ..." && git push

## Step 5: Report compact summary — what was fixed and whether it succeeded.
```

### Setup

```bash
# 1. Deploy companion scripts
cp hermes-cortex/scripts/orch-moses-inbox-remediate.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/orch-moses-inbox-remediate.sh

# 2. Create the cron
hermes cron create \
  --name "process-agent-messages" \\
  --schedule "every 10m" \
  --prompt "Paste the recipe above" \
  --enabled-toolsets terminal,file,web
```

### Prerequisites

- `orch-check-agent-messages.sh` cron running every 10m (detects messages + writes markers)
- Peer agents sending fix requests to agent inbox (topics: general, all, luke, <agentname>)

---

## Tips & Troubleshooting

**Cron jobs run without user presence** — they cannot use interactive tools,
ask questions, or use the `memory` tool. Use file I/O instead (read_file,
write_file, patch, terminal).

**no_agent jobs** run a single script with no LLM overhead. Use these for
mechanical, repeatable tasks (threshold checks, service recovery).

**LLM-driven jobs** are more expensive but can make judgment calls.
Use these for tasks that need reasoning (pruning, analysis, briefing).

**Keep prompts self-contained** — cron jobs have no memory of previous runs
or your conversation history.

**Deliver to "origin"** to send results back to the same chat the cron was
created from. Use "local" for silent background jobs.

**Test before deploying:** Run `hermes cron run <job-id>` to test a job
immediately without waiting for the schedule.

---

## Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-06-15 | 1.3.0 | Added Moses Inbox Remediation Processor recipe — auto-remediate agent-inbox fix requests within 10 min. Companion script, marker-based pipeline, verification-fix cycle. |
| 2026-06-05 | 1.0.0 | Initial release — 10 recipes |
