#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-dream-crons.sh — OPTIONAL mycortex dream layer
#
#  The dream layer is an EXTRA — removable per-agent. It is NOT
#  part of the standard install-crons.sh fleet set, so the doctor
#  does not expect these crons and non-participating agents never
#  get them.
#
#  Three tiers (see docs/design/mycortex-dream-layer.md):
#    agent-mycortex-dream-nightly  0 23 * * *   digest → dreams/YYYY-MM-DD.md
#    agent-mycortex-dream-weekly   0 3 * * 6    lessons + scripture → -weekly.md
#    agent-mycortex-dream-monthly  0 3 1 * *    time-lapse + gaps → YYYY-MM-monthly.md
#
#  Every run writes back into ~/brain/<agent>/dreams/ and appends
#  to INDEX.md so dreams connect across runs.
#
#  Usage:
#    bash install-dream-crons.sh              # create missing dream crons
#    bash install-dream-crons.sh --dry-run    # show what would be created
#    bash install-dream-crons.sh --force      # recreate all dream crons
#    bash install-dream-crons.sh --uninstall  # remove dream crons (dreams kept)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
source "${SCRIPT_DIR}/os-config.sh"

# ── Source project .env ──────────────────────────────────
ENV_FILE="${HOME}/hermes-cortex/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi

HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
CRON_JOBS_FILE="${HERMES_HOME}/cron/jobs.json"
SCRIPTS_DIR="${HOME}/.hermes-cortex/scripts"
HERMES_CMD=""
for candidate in hermes "${HERMES_HOME}/hermes-agent/venv/bin/hermes"; do
  if command -v "$candidate" &>/dev/null; then
    HERMES_CMD="$candidate"
    break
  fi
done

CYAN="\033[0;36m"; GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; RESET="\033[0m"
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
fail()  { printf "${RED}✗${RESET} %s\n" "$*"; }

UNINSTALL=false
FORCE=false
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --uninstall) UNINSTALL=true ;;
    --force)     FORCE=true ;;
    --dry-run)   DRY_RUN=true ;;
    *) warn "Unknown arg: $arg (ignored)" ;;
  esac
done

# ── Helper: does a cron exist? ───────────────────────────
cron_exists() {
  local name="$1"
  if command -v python3 &>/dev/null && [[ -f "$CRON_JOBS_FILE" ]]; then
    python3 -c "
import json, sys
try:
    with open('$CRON_JOBS_FILE') as f:
        data = json.load(f)
    jobs = data.get('jobs', []) if isinstance(data, dict) else data
    sys.exit(0 if any(isinstance(j, dict) and j.get('name') == '$name' for j in jobs) else 1)
except Exception:
    sys.exit(1)
"
  fi
}

# ── Helper: remove a cron ────────────────────────────────
remove_cron() {
  local name="$1"
  if ! cron_exists "$name"; then
    info "Skipping $name (not installed)"
    return 0
  fi
  local job_id
  job_id=$(python3 -c "
import json, sys
try:
    with open('$CRON_JOBS_FILE') as f:
        data = json.load(f)
    jobs = data.get('jobs', []) if isinstance(data, dict) else data
    for j in jobs:
        if isinstance(j, dict) and j.get('name') == '$name':
            sys.stdout.write(j.get('id', ''))
            sys.exit(0)
except Exception:
    sys.exit(1)
sys.exit(1)
")
  if [[ -n "$job_id" && -n "$HERMES_CMD" ]]; then
    "$HERMES_CMD" cron remove "$job_id" >/dev/null 2>&1 && info "Removed $name ($job_id)" || warn "Failed to remove $name"
  elif [[ -n "$job_id" ]]; then
    warn "No hermes CLI found — remove $name manually (id: $job_id)"
  fi
}

# ── Helper: create a cron (mirrors install-crons.sh) ─────
# NOTE: the hermes CLI (`cron create`) does NOT expose --toolsets. The
# toolsets argument here is carried for documentation only; after create,
# apply enabled_toolsets via the cronjob MCP tool (update) so LLM crons
# stay lean — design says ["terminal","file"] for the dream tiers.
create_cron() {
  local name="$1" schedule="$2" script="$3" prompt="$4" skill="$5" toolsets="$6" deliver="$7" workdir="$8" no_agent="$9"
  if cron_exists "$name"; then
    if ! $FORCE; then
      info "Skipping $name (already exists)"
      return 0
    fi
  fi
  if $DRY_RUN; then
    info "[DRY-RUN] Create cron: $name  (schedule=$schedule, no_agent=$no_agent)"
    return 0
  fi
  if [[ -z "$HERMES_CMD" ]]; then
    warn "No hermes CLI found — cannot create $name"
    return 1
  fi
  local cmd=("$HERMES_CMD" "cron" "create" "--name" "$name" "--schedule" "$schedule")
  [[ -n "$script"  ]] && cmd+=("--script" "$script")
  [[ -n "$prompt"  ]] && cmd+=("--prompt" "$prompt")
  [[ -n "$skill"   ]] && cmd+=("--skill" "$skill")
  [[ -n "$deliver" ]] && cmd+=("--deliver" "$deliver")
  [[ -n "$workdir" ]] && cmd+=("--workdir" "$workdir")
  if [[ "$no_agent" == "true" ]]; then cmd+=("--no-agent"); fi
  if "${cmd[@]}" >/dev/null 2>&1; then
    info "Created $name"
  else
    warn "CLI create failed for $name — create via cronjob tool with deliver=origin (chat must be live)"
  fi
}

# ── Uninstall ────────────────────────────────────────────
if $UNINSTALL; then
  echo ""
  printf "${CYAN}━━━ Removing Mycortex Dream Crons (dreams kept in ~/brain/<agent>/dreams/) ━━━${RESET}\n\n"
  for job in \
    "agent-mycortex-dream-monthly" \
    "agent-mycortex-dream-nightly" \
    "agent-mycortex-dream-weekly"; do
    remove_cron "$job"
  done
  # Remove the installed-marker so the doctor stops expecting dream crons
  rm -f "${HOME}/.hermes-cortex/state/dream-layer-installed"
  info "Dream crons removed. Dream files are knowledge — kept."
  exit 0
fi

# ── Install ──────────────────────────────────────────────
echo ""
printf "${CYAN}━━━ Optional Mycortex Dream Layer ━━━${RESET}\n\n"
warn "This is an OPTIONAL extra — skip if you don't want nightly/weekly/monthly brain dreams."
info "Docs: docs/design/mycortex-dream-layer.md"

# Tier 3 — Monthly arc (1st of month 03:00)
create_cron "agent-mycortex-dream-monthly" "0 3 1 * *" \
  "" \
  "You are the monthly mycortex dream arc — Tier 3 of the dream layer. The mycortex knowledge brain indexes markdown across the fleet. Your job: the time-lapse view — how the work evolved this month, what scale grew, and what the brain is missing.

## Steps
1. TIME-LAPSE: \`git -C ~/hermes-cortex log --oneline --since=\"30 days\" | wc -l\` for the month's commit count; \`git -C ~/hermes-cortex log --oneline --since=\"30 days\" | head -30\` to see the work arc; \`ls ~/brain/lessons/ | wc -l\` for lesson scale; \`mycortex stats\` for brain scale
2. \`mycortex list -n 30\` — what's fresh; pick 3-5 pages that capture the month's themes
3. KNOWLEDGE-GAP PROBE: take 3-5 topics the month's work clearly touched (from the git log themes) and run \`mycortex search \"<topic>\" --limit 3\` for each. Topics with zero or weak results become explicit flags: \"the brain knows nothing about X yet.\"
4. Write a ~300-word monthly arc: the shape of the month, the scale numbers, the gaps found. Reference 2-3 prior dreams from the INDEX.
5. WRITE-BACK (mandatory): create \`~/brain/<profile>/dreams/\` if missing, write_file \`~/brain/<profile>/dreams/YYYY-MM-monthly.md\`, then append \`YYYY-MM | <title> | <one-line summary>\` to \`~/brain/<profile>/dreams/INDEX.md\` (create if missing). PROFILE name — NOT hostname (tenant boundary): check HERMES_PROFILE env, then AGENT_NAME env, then hostname — NEVER scan ~/.hermes/profiles/*/ (the first entry alphabetically is NOT the active profile; observed 2026-08-06: 'personal' dir exists but the session runs as esther).
6. DREAM→TODO BRIDGE (Option A — knowledge gaps): for the top 4 gappy topics from Phase 3, run \`python3 ~/.hermes-cortex/scripts/dream-todo-bridge.py add-gap --topic \"<topic>\" --agent <profile> --month YYYY-MM\`. The script enforces dedup (skips topics already covered by a pending todo) and priority 1. If the script prints SKIP, note it in the dream; if it prints \`todo <uuid8>\`, record it in Phase 3b.
7. DREAM→TODO BRIDGE (Option B — insight triage): after writing the dream, ask: does any insight imply a concrete verifiable action (verb + object + outcome)? At most 2 per run. For each, run \`python3 ~/.hermes-cortex/scripts/dream-todo-bridge.py add-insight --content \"<verb> <object> — <outcome>\" --agent <profile> --date YYYY-MM-DD --priority 2\` (priority 1 for doc/write/probe/build, 2 for fix/verify/rollout). Observational/reflective insights are NEVER todos — they stay in the dream file.

Real numbers only — every count from an actual command. Real connections only — never fabricate. If the brain is genuinely empty, output exactly [SILENT].

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values. Everything else stays: dashes, colons, spacing, line breaks.

agent-mycortex-dream-monthly (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Time-lapse: 142 commits this month
- Work arc: cron delivery fixes → governance hardening → dream layer build
- Lessons grew 631 → 645; brain grew 1681 pages / 29615 chunks

Phase 2 — Month themes: 3 captured in fresh pages
- Delivery discipline (explicit telegram targets)
- Governance sizing (one cycle = one deliverable)
- Knowledge brain self-construction (mycortex + dreams)

Phase 3 — Knowledge gaps: 2 topics the work touched but the brain has nothing on
- [gap] theme-of-the-month-alpha — zero strong hits
- [gap] theme-of-the-month-beta — weak hits only

Phase 3b — Gaps → todos: 2 learning todos added
- todo fc602f04: learn theme-of-the-month-alpha (priority 1)
- todo 0cbb57e9: learn theme-of-the-month-beta (priority 1)

Phase 4 — Monthly dream:
The month's arc is the fleet learning to close its own feedback loops — every fix this month made the next failure louder and the next lesson more reusable. The gaps are the honest edges: what we did but haven't yet understood well enough to write down.

Phase 4b — Actionable: 1 insight triaged to todo
- todo a85c2522: verify deepseek rollout on cisnet02 (priority 2) [from dream 2026-08-06]

Phase 5 — Written back: ~/brain/esther/dreams/2026-08-monthly.md (+ INDEX appended)

Result: 1 monthly arc written to brain and delivered.

📊 deepseek-v4-flash (deepseek) | \$0.006/run ≈ \$0.01/mo" \
  "" \
  "terminal,file" \
  "origin" \
  "" \
  "false"

# Tier 1 — Nightly digest (23:00)
create_cron "agent-mycortex-dream-nightly" "0 23 * * *" \
  "" \
  "You are the nightly mycortex dream digest — Tier 1 of the dream layer. The mycortex knowledge brain indexes markdown across the fleet. Your job: surface what the brain noticed today AND write the dream back into the brain so it accumulates.

## Steps
1. \`mycortex list -n 20\` — see what's fresh across the brain (recently synced pages with timestamps)
2. Use session_search to find today's sessions — what was actually worked on today
3. Pick 2-3 pages/sessions that seem related or interesting; run \`mycortex search \"<shared topic>\" --limit 3\` to find the connection
4. Write a short, warm digest (~100-150 words): the insight, pattern, or connection — the brain telling you something interesting
5. WRITE-BACK (mandatory): determine your PROFILE name (NOT hostname — profile is the tenant boundary: check HERMES_PROFILE env, then AGENT_NAME env, then hostname — NEVER scan ~/.hermes/profiles/*/ (the first entry alphabetically is NOT the active profile; observed 2026-08-06: 'personal' dir exists but the session runs as esther)). Create \`~/brain/<profile>/dreams/\` if missing, then write_file \`~/brain/<profile>/dreams/YYYY-MM-DD.md\` containing the digest. Then append a one-line entry to \`~/brain/<profile>/dreams/INDEX.md\` (create if missing) in format: \`YYYY-MM-DD | <short title> | <one-line summary>\`.
6. Before writing, read \`~/brain/<profile>/dreams/INDEX.md\` if it exists and reference 1-2 prior dreams in your digest when natural (the brain remembering its own dreaming).
7. DREAM→TODO BRIDGE (Option B — insight triage): after writing the dream, ask: does any insight imply a concrete verifiable action (verb + object + outcome)? At most 2 per run. For each, run \`python3 ~/.hermes-cortex/scripts/dream-todo-bridge.py add-insight --content \"<verb> <object> — <outcome>\" --agent <profile> --date YYYY-MM-DD --priority 2\` (priority 1 for doc/write/probe/build, 2 for fix/verify/rollout). Observational/reflective insights are NEVER todos — they stay in the dream file. The script enforces dedup and tenant-scoping; if it prints SKIP, note it in the digest.

Real connections only — never fabricate page relationships; every claimed link must come from an actual mycortex search result or session. If the brain is genuinely empty (no pages, no sessions), output exactly [SILENT].

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values. Everything else stays: dashes, colons, spacing, line breaks.

agent-mycortex-dream-nightly (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Fresh pages: 3 pages surfaced from the brain
- ops/scripts/agent/agents-doc-audit.py (2026-08-05 20:01)
- docs/cron-schedules.md (2026-08-06 09:00)
- skills/devops/mycortex/SKILL.md (2026-08-05 23:46)

Phase 2 — Today's work: 2 sessions synthesized
- Threat-pipeline delivery fix (origin=null silent-cron bug)
- Mycortex dream layer build (3-tier design)

Phase 3 — Dream digest:
Today the brain was thinking about keeping itself honest — the doc-audit work and the cron delivery fixes are two halves of the same habit: nothing stale survives. Yesterday's dream noted the same theme — the thread is holding.

Phase 4 — Written back: ~/brain/esther/dreams/2026-08-06.md (+ INDEX appended)

Phase 4b — Actionable: 1 insight triaged to todo
- todo a85c2522: verify deepseek rollout on cisnet02 (priority 2) [from dream 2026-08-06]

Result: 1 dream written to brain and delivered.

📊 deepseek-v4-flash (deepseek) | \$0.006/run ≈ \$0.18/mo" \
  "" \
  "terminal,file" \
  "origin" \
  "" \
  "false"

# Tier 2 — Weekly deep dream (Sat 03:00)
create_cron "agent-mycortex-dream-weekly" "0 3 * * 6" \
  "" \
  "You are the weekly deep mycortex dream — Tier 2 of the dream layer. The mycortex knowledge brain indexes markdown across the fleet. Your job: find the connections the week's work created that nobody has noticed, synthesize the week's saved lessons, and write the dream back into the brain.

## Steps
1. \`mycortex list -n 30\` — see what's fresh across the brain this week
2. Pick 3-5 pages that seem related or interesting (different sources preferred); for each pair run \`mycortex search \"<shared topic>\" --limit 3\` to map connections
3. LESSON SYNTHESIS: \`ls ~/brain/lessons/ | tail -20\` to find this week's lesson files (dated this week), read 3-5 of them, and identify the recurring pattern — what class of mistake/lesson keeps appearing. Name it explicitly.
4. SCRIPTURE CONNECTION: if \`~/brain/<profile>/bible/\` exists (profile name — NOT hostname: check HERMES_PROFILE env, then AGENT_NAME env, then hostname — NEVER scan ~/.hermes/profiles/*/ (the first entry alphabetically is NOT the active profile; observed 2026-08-06: 'personal' dir exists but the session runs as esther)), read \`~/brain/<profile>/bible/INDEX.md\` and the most recent book file; connect the week's scripture insight to the week's actual work themes. If no bible dir exists, skip this step gracefully (do NOT fail — this keeps the dream portable to all agents).
5. Write a warm ~200-250 word dream: the insight, the pattern, the thread that ties the week together.
6. WRITE-BACK (mandatory): create \`~/brain/<profile>/dreams/\` if missing, write_file \`~/brain/<profile>/dreams/YYYY-MM-DD-weekly.md\`, then append \`YYYY-MM-DD | <title> | <one-line summary>\` to \`~/brain/<profile>/dreams/INDEX.md\` (create if missing).
7. Read the INDEX first and reference prior dreams when natural.
8. DREAM→TODO BRIDGE (Option B — insight triage): after writing the dream, ask: does any insight imply a concrete verifiable action (verb + object + outcome)? At most 2 per run. For each, run \`python3 ~/.hermes-cortex/scripts/dream-todo-bridge.py add-insight --content \"<verb> <object> — <outcome>\" --agent <profile> --date YYYY-MM-DD --priority 2\` (priority 1 for doc/write/probe/build, 2 for fix/verify/rollout). Observational/reflective insights are NEVER todos — they stay in the dream file. The script enforces dedup and tenant-scoping; if it prints SKIP, note it in the dream.

Real connections only — never fabricate relationships. Every claimed link must come from an actual mycortex search result or file read. If the brain is genuinely empty, output exactly [SILENT].

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values. Everything else stays: dashes, colons, spacing, line breaks.

agent-mycortex-dream-weekly (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Fresh pages: 5 pages surfaced from the week
- ops/scripts/manage/agent-nginx-threat-pipeline.sh (2026-08-06 05:00)
- docs/cron-schedules.md (2026-08-06 09:00)
- skills/devops/mycortex/SKILL.md (2026-08-05 23:46)
- docs/design/mycortex-DESIGN.md (2026-08-05 23:40)
- docs/design/mycortex-dream-layer.md (2026-08-06 09:30)

Phase 2 — Connections mapped: 3 threads linking the week's work
- Thread 1: delivery discipline — cron targets and threat reports converged on visibility
- Thread 2: the brain's own story — mycortex design + dream layer built together
- Thread 3: hygiene as habit — stale-ref watchdog + doc audit enforce freshness

Phase 3 — Lessons synthesized: 3 of this week's lessons share one root
- Governance cycle sizing (bundled 4 deliverables → push cascade)
- Silent cron delivery (origin=null)
- Both are the same class: task too big, feedback too late

Phase 4 — Scripture connection (if bible dir exists): this week's reading on faithfulness met the lesson-synthesis finding — consistency over intensity.

Phase 5 — Dream:
This week the brain kept circling one idea: a system is only as alive as its feedback loops. The threat pipeline now reports where it used to whisper; the knowledge brain indexes the very docs that describe it. The recurring lesson — split the work, keep the loop tight — is the same lesson the week's scripture carried.

Phase 6 — Written back: ~/brain/esther/dreams/2026-08-08-weekly.md (+ INDEX appended)

Phase 6b — Actionable: 1 insight triaged to todo
- todo a85c2522: verify deepseek rollout on cisnet02 (priority 2) [from dream 2026-08-08]

Result: 1 weekly dream written to brain and delivered.

📊 deepseek-v4-flash (deepseek) | \$0.006/run ≈ \$0.03/wk" \
  "" \
  "terminal,file" \
  "origin" \
  "" \
  "false"

mkdir -p "${HOME}/.hermes-cortex/state"
touch "${HOME}/.hermes-cortex/state/dream-layer-installed"
info "Dream layer installed (marker set — doctor now expects these crons). Remove anytime: bash install-dream-crons.sh --uninstall"
