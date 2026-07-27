# Worked Example: Agent Inbox → Agent Bus Terminology Rename

**Date:** 2026-07-15
**Scope:** ~/hermes-cortex/docs/ — 17 files, 60+ patches
**Pattern:** Pattern H — Cross-file terminology rename

## Setup

The task was to update all docs referencing "agent inbox" as a current/primary
system to reference "Agent Bus" (the new PGMQ-based Postgres queue system).
The old file-based inbox is legacy/deprecated.

## Rules from user

- Replace "agent inbox" → "agent bus" where it describes the current system
- Add "(previously Agent Inbox)" on first mention in a doc
- Do NOT modify: agent-bus-setup.md, nginx configs, systemd units, ops/services/
- Do NOT change cron job names/definitions
- Keep legacy doc (agent-inbox-setup.md) as-is with stronger legacy framing

## Search Results

Three concurrent searches found 22+41+12 unique files touching the org:

| Pattern | Files found | Variation |
|---------|-------------|-----------|
| `agent.inbox` (regex) | 22 files | Both `agent inbox` and `agent-inbox` |
| `agent-inbox` (literal) | 19 files | Hyphenated form |
| `Agent Inbox` (literal) | 5 files | Title-cased form |

## Categorization Table

| File | Category | Notes |
|------|----------|-------|
| agent-inbox-setup.md | Legacy | Doc IS the legacy system; title marked "(Legacy)", deprecation notice strengthened |
| agent-bus-setup.md | Excluded | "already correct" per user; not modified |
| operations-reference.md | Change | Major section renamed; ports 8903→8905; architecture diagram; cron prompt examples |
| fleet-reference.md | Change | "Inbox method" → "Bus method"; "Moses inbox" → "Moses Agent Bus" |
| architecture.md | Skipped | Already used "Agent Bus" everywhere; no changes needed |
| pipeline-reference.md | Change | "Inbox broadcast" → "Agent Bus broadcast" (3 patches) |
| cron-job-recipes.md | Change | Recipe title, descriptions, changelog entry (cron names preserved) |
| cron-schedules.md | Change | Descriptions only (cron names preserved as Name-only) |
| a2a-architecture.md | Change | Warning banner, ports, diagram storage, server paths |
| a2a-deploy-notes.md | Change | Merged-into notice, ports, migration paths |
| agent-onboarding.md | Change | Architecture diagram, config entries, health guidance (full rewrite) |
| DOCS-INDEX.md | Change | Descriptions for agent-inbox-setup.md and health-push plist |
| migration-2026-07-08-hermes-to-cortex.md | Historical | Directory paths, service names in migration context |
| symlink-policy.md | Change | agent-inbox.conf → agent-bus.conf, directory map |
| service-layer-decision.md | Change | "agent-inbox" service scope → "agent-bus" |
| linux-service-layer.md | Change | Service name in fleet map, grep pattern |
| SKILLS-MANIFEST.md | Change | Skill descriptions (agent-inbox skill name kept as-is) |
| stale-paths-audit.md | Historical | Audit doc referencing the legacy file; minor annotation |
| cloud-deploy.md | Change | Security group table entry |
| integration-audit.md | Historical | Migration record of service files — intentional stale refs |
| elicit/2026-07-09_systemd-decision-party.md | Name-only | Service name in install command |
| research/enterprise-grade-hermes-cortex.md | Historical | Research about original design |
| docs/templates/com.hermes.health-push.plist | Excluded | systemd/launchd template; excluded per instructions |

## Key Pitfalls Encountered

### 1. Escape-drift on patch tool

When patching strings containing literal double-quote characters inside
markdown backticks, the old_string must match the file exactly. The
serialization layer may introduce backslash-escaped quotes (`\"`) in the
tool call, but the file has literal quote characters (`"`).

**Fix:** Always read the exact line from the file with `read_file(path)`,
then copy-paste it into old_string. Do not manually add backslashes.

### 2. Governance lock juggling

Multiple patch rounds on the same repo triggered governance enforcer
checks. The enforcer uses per-repo lock files and rejects patches if
the active lock's task_id doesn't match. When the lock was stale from
a prior session, needed to force-acquire. When mid-batch, the lock
persisted across all patches — scoring the cycle mid-batch caused the
lock to release prematurely.

**Fix:** Acquire ONE lock at the start of all patches. Score and release
only after ALL patches are verified. If the lock was left by a prior
session, use `begin_change(..., force=True)` to override.

### 3. replace_all vs individual patches

For multi-occurrence strings where every occurrence should change
identically, `replace_all=true` is correct. But when one occurrence is in
a historical context and another in a current-description context (both
using the same string), individual patches are needed to apply different
transformations.
