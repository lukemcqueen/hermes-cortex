---
name: doc-freshness
version: 1.1.0
category: devops
description: >-
  Ensure AGENTS.md and SOUL.md stay current across all agents and projects.
  Weekly audit, post-update broadcast, mandatory section gap detection, and
  multi-project awareness.
  **Model requirement:** The audit cron needs 64K+ context window. Pinned to
  deepseek-v4-flash. If you see "context below 64K minimum", pin the cron to
  a model with ≥64K context using cronjob(action='update', job_id=..., model={'provider': 'deepseek', 'model': 'deepseek-v4-flash'}).
platforms: [linux, macos]
metadata:
  hermes:
    tags: [docs, governance, agents, audit, broadcast, soul, freshness]
    related_skills: [orch-skill-lifecycle, agent-inbox, documentation-scope, repo-organization, cron-job-management]
---

# Doc Freshness — AGENTS.md + SOUL.md Governance

## What This Is

A cross-document freshness system that ensures AGENTS.md (fleet coordination rules) and SOUL.md (agent identity docs) don't drift from what the fleet expects. Five enforcement layers:

| Layer | What | Who runs | Frequency |
|-------|------|----------|-----------|
| **Template drift check** | `template-diff-check.py` runs during `cortex-update.sh` after every `git pull`. Compares local `~/.hermes/SOUL.md` against `docs/templates/SOUL.md` for missing sections, stale content markers, and deprecated patterns. | Each agent's own `cortex-update.sh` | Every `git pull` (typically daily) |
| **Weekly audit** | `agents-doc-audit.py` checks all SOUL.md + AGENTS.md for mandatory section *presence* | Moses (orchestrator) | Monday 7am KST |
| **Post-update broadcast** | Moses sends inbox message to all agents after modifying AGENTS.md or his SOUL.md | Moses (orchestrator) | On change |
| **Daily gap fill** | `orch-skill-lifecycle` cron (orchestrator) evaluates agent data, patches skills/SOUL.md. Non-orchestrators use the bus to submit learning reports. | Per-agent | Daily 04:00 (orchestrator) |
| **Session-start check** | Every agent reads AGENTS.md + own SOUL.md at session start | Each agent | Every session |

**Key insight:** The template drift check (Layer 1) is the earliest detection layer — it fires on every `git pull` before the agent even starts a work session. It detects *content* drift (stale markers, deprecated patterns), not just missing sections. The weekly audit catches anything structural that slipped through. The daily gap fill auto-recovers. The session-start check is the last resort.

### Template drift detection

The `template-diff-check.py` script (deployed via `cortex-update.sh` MAP) compares `~/.hermes/SOUL.md` against `docs/templates/SOUL.md`:

| Check | What it detects | Example |
|-------|----------------|---------|
| **Missing sections** | Template has a `## Section` the local copy lacks | Template has `Behavioral Principles` but local doesn't |
| **Stale content markers** | Key version markers missing from a section | Loop Governance should mention `MCP-enforced` but says `skip=self-destruct` |
| **Deprecated patterns** | Known-old language found in the file | `Strike 3 → propose`, `Three strikes → propose` |

Exit code 1 triggers a warning in the `cortex-update.sh` output. Silent (exit 0) means current.

**To resolve drift:**
```bash
diff ~/.hermes/SOUL.md ~/hermes-cortex/docs/templates/SOUL.md
# Merge changes, then re-run cortex-update to confirm
cortex-update --status
```

### First-time seeding

On first install, `install.sh` Step 9 copies `docs/templates/SOUL.md` to `~/.hermes/SOUL.md` if it doesn't already exist. New agents get the full template with all mandatory sections, behavioral principles, and enforcement workflow from day one.

## Mandatory Sections

### SOUL.md (every agent)
- Identity
- Core Mission
- Behavioral Principles (must include Loop Governance + Inbox Decision Framework + Inbox Audit Trail)
- Communication Style
- Scripture Insights

### AGENTS.md (per project)
- Excellence (core value — every action)
- Agent Execution Contract
- Loop Governance
- Inbox Message Decision Framework
- Doc Freshness: AGENTS.md + SOUL.md
- Governance lock (begin_change / end_change)
- Rule #10: Score Every Change
- Real execution, no simulation
- Pre-commit / pre-push hooks

**Size gate:** the doctor size-checks `~/.hermes/AGENTS.md` exactly like
SOUL.md — WARN >15K, FAIL >20K (`check_repo` in cortex_doctor/checks.py).
Only the hermes-cortex fleet constitution is gated; other repos' AGENTS.md
have no size limit. A WARN here can't be cleared by re-syncing (repo and
deployed are the same size) — it needs a real trim of the repo source, or a
deliberate threshold re-baseline. Trimming is orchestrator-owned
(AGENTS.md is in `docs/orchestrator-only-paths.txt`).

## Triggers

Use this skill when:
- Setting up a new agent (seed their SOUL.md from the template)
- AGENTS.md or SOUL.md has been modified (broadcast to other agents)
- It's Monday morning (run the weekly audit)
- A cron delivered a `Missing: X, Y, Z` warning from the audit
- `cortex-update.sh` reports `⚠ Template drift detected` after a pull
- User asks "how do agents get notified when docs change?"
- User asks to update or audit the README — verify every section matches current repo state, paths exist, counts are accurate, installation instructions work
- **You see** `ValueError: Model X context (N tokens) below 64K minimum` — the cron's model doesn't have enough context window. Fix it by pinning a 64K+ model (see "Model Requirements" below)

## Model Requirements

The weekly `local-agent-agents-doc-audit` cron is an **LLM-driven cron** (not a no_agent script). The LLM that processes the audit data needs a **64K+ token context window** because the audit script's output can be large (file contents, diffs, section analysis).

**If the cron fails with:**
```
RuntimeError: HTTP 401 → ValueError: Model qwen2.5-coder:3b context (8,192 tokens) below 64K minimum
```

**The fix is to pin the cron to a model with ≥64K context:**

```bash
# 1. Find the cron job ID
cronjob action=list  # look for 'local-agent-agents-doc-audit'

# 2. Pin it to a cloud model with large context
cronjob action=update job_id=9dd475df2ed1 \
  model.provider=deepseek \
  model.model=deepseek-v4-flash

# 3. Or pin it to any model with 64K+ context
cronjob action=update job_id=9dd475df2ed1 \
  model.provider=openrouter \
  model.model=anthropic/claude-sonnet-4
```

**Why this happens:**
1. The cron is LLM-driven (not no_agent) — it loads the audit script output, then sends it to an LLM for analysis
2. If the cron's model/provider isn't pinned (model_snapshot=null), it uses whatever model is active in the session
3. When cloud API keys are invalid/expired (HTTP 401), Hermes falls back to the local Ollama model
4. The local model `qwen2.5-coder:3b` only has 8K context — below the 64K minimum Hermes requires for cron tasks with data-collection scripts
5. Result: the cron fails with no output

**Prevention:** Always pin LLM-driven crons that use `script` (data-collection mode) to a model with ≥64K context. If a cron has `no_agent=false` and a `script` field, pin its model. Use `model_snapshot` or set it explicitly on create/update.

**Which models are safe (64K+):**
- `deepseek-v4-flash` (deepseek) — 128K context ✅
- `anthropic/claude-sonnet-4` (openrouter) — 200K context ✅
- Any cloud model with ≥64K context

**Which models will fail:**
- `qwen2.5-coder:3b` (local Ollama) — 8K context ❌
- Any local model with <64K context ❌
- Any model that falls through to the 8K default ❌

## Workflow

### 1. Weekly Audit

```bash
python3 ~/.hermes-cortex/scripts/agents-doc-audit.py
# → report with ✅/⚠️/❌ per file
python3 ~/.hermes-cortex/scripts/agents-doc-audit.py --json
# → machine-readable for cron
```

The cron `local-agent-agents-doc-audit` runs this every Monday 7am KST (data-collection mode → LLM analysis).

**What the audit checks:**
- Each configured SOUL.md for all mandatory sections
- Each configured AGENTS.md for all mandatory sections
- Git freshness (disk vs last commit for that file)
- Reports missing sections + stale warnings

### 1b. Pre-Commit Hook Check (--repo mode)

The same `agents-doc-audit.py` tool doubles as a pre-commit gate. The
pre-commit hook (`pre-commit-score`) calls it on every commit:

```bash
python3 ~/.hermes-cortex/scripts/agents-doc-audit.py --repo /path/to/repo --json
```

**Exit codes:**
| Code | Meaning |
|------|---------|
| 0 | All required sections present → commit allowed |
| 1 | Missing required sections → commit blocked (lists which) |
| 2 | No AGENTS.md found → commit blocked |

**Required sections for hook mode** (defined in `hook_sections` config key):
- Agent Execution Contract
- Rule #10: Score Every Change
- Real execution, no simulation
- Pre-commit / pre-push hooks

This is the **same tool** as the weekly audit — not a separate script.
The redundant `check-agents-dot-md.py` was merged into this tool and
deleted (July 2026). `agents-doc-audit.py` is the single source of truth
for all AGENTS.md + SOUL.md auditing.

**Config:** Default config checks:
- `~/.hermes/SOUL.md` (Moses)
- `~/hermes-cortex/AGENTS.md` (hermes-cortex)

**Extending the config:**
Pass a custom YAML config with `--config path/to/config.yaml`:
```yaml
soul_files:
  - path: "~/.hermes/SOUL.md"
    agent: "Moses"
    mandatory_sections:
      - Identity
      - Core Mission
      - Behavioral Principles
      - Communication Style
      - Scripture Insights
agents_files:
  - path: "~/hermes-cortex/AGENTS.md"
    repo: "hermes-cortex"
    mandatory_sections:
      - Agent Execution Contract
      - Loop Governance
      - Inbox Message Decision Framework
      - Doc Freshness
      - Governance lock
      - Rule #10: Score Every Change
      - Real execution, no simulation
# Optional: hook sections for pre-commit gate
hook_sections:
  - Agent Execution Contract
  - Rule #10: Score Every Change
  - Real execution, no simulation
  - Pre-commit / pre-push hooks
```

### 2. Post-Update Broadcast

When AGENTS.md or SOUL.md changes, notify all agents:

```bash
# Dry run first
python3 ~/hermes-cortex/ops/scripts/agent/agents-doc-broadcast.py AGENTS.md \
  "Added Inbox Message Decision Framework section" --dry-run

# Then actually broadcast (produces structured output for agent to send via inbox)
python3 ~/hermes-cortex/ops/scripts/agent/agents-doc-broadcast.py AGENTS.md \
  "Added Inbox Message Decision Framework section"
```

The broadcast script outputs an inbox message template. The orchestrator (Moses) then sends it via `mcp_agent_inbox_inbox_send` to all agents.

**Target agents:** gisu, joseph, kustos, titus, esther (always CC luke)

### 3. Adding a New Mandatory Section / Fleet-Wide Core Value

A new principle that must govern EVERY agent (excellence, a safety rule, a
quality bar) is not done when it lands in one file. Non-Hermes coding agents
(Claude/Codex/pi) read **only AGENTS.md** (they have no user.md), the herd
reads AGENTS.md + SOUL.md, and project agents read the seed. A fleet-wide value
propagates through FOUR surfaces in one change, or it reaches a subset:

1. **`AGENTS.md`** — the universal file; the vector to non-Hermes agents.
2. **`docs/templates/AGENTS.seed.md`** — every new project repo gets it.
3. **`docs/templates/SOUL.md`** — Core Traits/Behavioral Principles, so the
   herd's identity carries it alongside the ethics.
4. **`CLAUDE.md`** — titusclaude's governance contract (doctor requires it in
   dev repos where a Claude agent is configured).

**`USER.md` is NOT one of the four.** USER.md holds personal context about the
human; engineering standards, quality bars, and review posture belong in
AGENTS.md. Keep a _user-owns-personal-only_ note in `docs/templates/USER.seed.md`
so the boundary is explicit, and drop engineering-preference stubs (e.g. a
`Testing:` line in Preferences) out of the seed when the value moves to AGENTS.

**Propagation is NOT uniform — pair each non-auto-syncing surface with a doctor
WARN so agents are told to reconcile.** `cortex-update` auto-syncs AGENTS.md
(`~/.hermes/AGENTS.md`), SOUL.md (soul-merge/soul-sync), and skills; it does
NOT touch CLAUDE.md copies already installed in dev repos, and it NEVER touches
USER.md (`~/.hermes/memories/`, Hermes-owned, deliberately unregistered so a
deploy cannot clobber a personalized copy). So "agents pull + cortex-update get
the new value" is only true for three surfaces — the other two silently keep
the old content unless a check flags them. For each non-auto-syncing surface add
a doctor check that WARNs (never auto-overwrites — both are user/project-owned),
and size the PROBE to how the file personalizes:
- **User-owned file (USER.md) → mtime-newer nudge, never a content compare.** A
  content hash against the seed FAILs on every healthy personalized copy, so the
  check WARNs when `templates/USER.seed.md` is NEWER than the live file ("template
  changed — diff and merge relevant guidance"). mtime-only; the nudge clears when
the human edits theirs.
- **Project-adapted file (per-repo CLAUDE.md) → match the exact stable heading,
  not a bare token.** A project copy legitimately adapts the body, so probing for
the bare word "Excellence" false-flags a repo that reworded the text but kept the
contract. Probe for the full fleet heading ("## Excellence — Core Value, Every
Action"); presence = current even when the body is adapted, absence = stale.

Then:

1. Add the section to `docs/templates/SOUL.md` (the reference template)
2. Add the section to `DEFAULT_CONFIG` in `agents-doc-audit.py`:
   - Under `agents_files[].mandatory_sections` for weekly audit coverage
   - Under `hook_sections` if the pre-commit hook should enforce it too
3. Update the `orch-skill-lifecycle` skill to cover the new section in its evaluation criteria, or update the `soul-refinement` fallback skill's Channel C mandatory sections list
4. Run `agents-doc-audit.py` to verify the new section shows as "missing" on current files
5. Broadcast the change: `agents-doc-broadcast.py AGENTS.md "Added Doc Freshness section"`
6. Patch the affected SOUL.md / AGENTS.md files

### 4. Extending to Other Projects

**Other repos are NOT the fleet constitution.** Only `hermes-cortex/AGENTS.md`
is synced to every agent's `~/.hermes/AGENTS.md` (cortex-update.sh),
orchestrator-owned (`docs/orchestrator-only-paths.txt`), and size-gated by the
doctor (WARN >15K, FAIL >20K). Every other repo's AGENTS.md = the **mandatory
core** (the `hook_sections` below) **plus repo-specific content** — build
commands, conventions, architecture. Start from
`docs/templates/AGENTS.seed.md`; never copy the fleet constitution into a
project repo, and never let a project AGENTS.md grow to constitution size.

Add new AGENTS.md files from other repos to the audit config:
```yaml
agents_files:
  - path: "~/my-other-project/AGENTS.md"
    repo: "my-other-project"
    mandatory_sections:
      - Agent Execution Contract
      - Loop Governance
```

The cron script needs updating too if you want those paths checked in the automated weekly scan (the cron uses the default config).

## Template Location

The canonical SOUL.md template lives at:
```
~/hermes-cortex/docs/templates/SOUL.md
```

It includes all mandatory sections with placeholder text. New agents should copy this to `~/.hermes/SOUL.md` and customize.

## Integration with orch-skill-lifecycle

The `orch-skill-lifecycle` skill's daily 04:00 KST run handles automatic gap filling:
- Scans SOUL.md for missing mandatory sections from the template
- Patches gaps using template structure as reference
- Marks additions with `<!-- Added YYYY-MM-DD via orch-skill-lifecycle -->`

This means even if broadcast is missed, the gap is closed within 24 hours.

## Pitfalls

- **Don't hardcode the file path list in the audit script** — use config for custom paths
- **Don't skip the broadcast** — other agents have no way to know AGENTS.md changed unless you tell them
- **Don't edit protected files** — `.hermes/hermes-agent/docker/SOUL.md` is a Hermes-bundled system prompt, not an agent SOUL
- **Don't add one-off session artifacts as mandatory sections** — a section must apply to every agent, not just today's task
- **A fleet-wide value landing in only ONE of its four surfaces is a partial
  propagation** — AGENTS.md, AGENTS.seed.md, SOUL.md, and CLAUDE.md each reach a
different audience (non-Hermes agents read only AGENTS.md). Adding a section
solely to the main AGENTS.md skips every fresh project and the non-Hermes
dev agent. Land all four in one change and reconcile the wording across them;
seeding an outdated copy (e.g. the older "prefer over-engineering" bullet)
means the deployed agents and the fresh-project agents disagree on the rule.
- **Seed/template content must be SELF-CONTAINED** — AGENTS.seed.md and
  CLAUDE.md are read by non-Hermes coding agents (Claude/Codex/pi) that load
  NO SOUL.md and often no memory. A cross-reference to another file's principle
  ("per SOUL P11") is a dangling pointer there. When a new section is added to
  the fleet AGENTS.md AND must reach non-Hermes agents, restate it in the seed
  without the SOUL/other-file reference, or drop the reference — do not let
  the seeded copy cite a document the reader will never load.
- **The stale flag is normal mid-session** — only worry if it persists through a commit cycle
- **Don't build a second AGENTS.md checker** — `agents-doc-audit.py` is the canonical tool. Before creating any new script, search existing tools that already handle the domain. The `check-agents-dot-md.py` → `agents-doc-audit.py` merge (July 2026) was caused by not searching first.
- **`template-diff-check.py` is a structural/language check, not a content audit** — it detects missing sections and stale markers, but doesn't verify the quality or completeness of the content within those sections. The weekly `agents-doc-audit.py` and daily `orch-skill-lifecycle` cron handle content-level gap filling.
- **Template drift check only fires if you run `cortex-update.sh`** — agents that never pull or update will never see the template drift warning. The weekly audit and daily `orch-skill-lifecycle` cron are the fallback for those agents.
- **README accuracy decays faster than agent docs** — the README is public-facing and describes install methods, scripts, paths, and counts that drift with every commit. After any significant merge (new scripts, reorganized directories, new deploy artifacts), check `docs/DOCS-INDEX.md` AND `README.md` against the actual repo tree. A stale README is how new users get stuck on first install.
- **Model pinning is required** for LLM-driven crons with data-collection scripts. If a cron fails with "context below 64K minimum", pin its model to one with >=64K context. Check `cronjob action=list` for `model: null` on LLM-driven crons and pin them.
- **Template-merge tools must REBUILD when the template shrinks, never append (2026-08-03).** `soul-merge.py` appended the new 12-principle template on top of stale pre-consolidation 34-principle content — stacking 46 principles and blowing the SOUL size budget (26,957 B, doctor FAIL). The trap: after the first bad merge, every template title IS present in the copy, so "missing titles" detection reports up-to-date and the balloon sticks forever. Fix pattern: detect consolidation by **count mismatch** (`len(template) < len(agent)`) gated on stale titles actually present (titles in the PREVIOUS template but NOT the current one — surviving titles like "Loop Governance" exist in both and must not re-trigger). On consolidation, rebuild the section from the template as authoritative, dropping stale template-origin principles while preserving genuinely agent-specific ones (title never in any template version, checked via git). Verify idempotency: run 1 rebuilds, runs 2+ report up-to-date with byte-stable content. A re-baseline of the template is the documented response to intentional restructuring — the merge tool must follow, not fight it.
