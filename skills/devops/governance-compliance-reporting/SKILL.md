---
name: governance-compliance-reporting
version: 1.0.0
category: devops
description: Review agent commits for enforcement compliance.
platforms: [linux, macos]
related_skills:
  - cortex-preflight
  - repo-health-review
  - code-review
---

# Governance Compliance Reporting

Systematic review of agent commits against repo governance rules. Produces a structured report showing which commits touched enforcement-critical paths, by which agent, and what action is needed.

## When to Use

- User says "check these commits for enforcement violations"
- User says "agents overwrote my enforcement work — review and undo"
- Before reverting a batch of commits, to assess what actually changed and what was legitimate
- When investigating whether non-orch agents modified orchestrator-only paths

## Workflow

### Phase 1: Gather Metadata

For each commit in the batch, collect:

```bash
# Author and committer (may differ — agent pushes using git identity of another agent)
git log -1 --format="Author: %an <%ae>%nCommitter: %cn <%ce>%nDate: %ai" <commit-hash>

# File-level summary
git show --stat <commit-hash>

# What orchestrator-only paths were touched
git diff --name-only <commit-hash>^..<commit-hash>
```

Cross-reference changed paths against `docs/orchestrator-only-paths.txt`:

```
ops/scripts/          ops/install/          plugins/
mcp-servers/          skills/               .hermes-cortex/hooks/
cortex_doctor/        tests/                profiles/
docs/templates/       AGENTS.md
```

### Phase 2: Classify Each Commit

| Class | Pattern | Response |
|-------|---------|----------|
| **User commit** | Author is the human (Luke, fleet-operator, etc.) | Leave alone — legitimate |
| **Orchestrator commit** | Author is Moses or Esther, path is in restricted list | Likely legitimate enforcement work |
| **Non-orch agent commit** | Author is an agent, path is in restricted list | **🔴 VIOLATION** — needs review/revert |
| **Doc-only** | Only changed docs/templates/ or AGENTS.md | Low severity — but still restricted |
| **Enforcement-impacting** | Changed pre-commit-score, plugins/*, mcp-servers/*, .hermes-cortex/hooks/* | **🔴 CRITICAL** — governance mechanism itself |

**Pitfall — author identity is unreliable:** Multiple agents may share the same git identity (`Moses (Hermes Agent) <moses@hermes-agent.local>`). The git author field alone cannot distinguish between Moses on the orchestrator machine vs Joseph running with the same config. Cross-reference with machine identity from the push source when available.

### Phase 3: Assess Enforcement Impact

For commits touching enforcement-critical paths, evaluate:

| File | What to check |
|------|---------------|
| `pre-commit-score` | Did the STAGED_FILES guard change? Was orchestrator-only path checking altered or removed? |
| `plugins/governance-enforcer/__init__.py` | Did the skills gate change? Was the blocking logic relaxed? Did ALL_TOOLS gate get changed to WRITE_TOOLS only? |
| `plugins/hermes-governance-enforcer/__init__.py` | Same as above (older plugin path). Did the skills list change (8 vs 10)? Did exemptions change? |
| `mcp-servers/loop-gov-mcp.py` | Was the DOGFOOD auto-deploy gate added, removed, or changed? Was the file gutted and rebuilt? |
| `.hermes-cortex/hooks/*` | Did hook symlink targets change? Did content drift from repo source? |

### Phase 4: Distinguish Damage from Legitimate Fixes

A commit to an enforcement-critical path is NOT automatically damage. Evaluate:

**Legitimate (keep):**
- Fixing a dead-code bug in the enforcer (e.g., `STAGED_FILES=''` → populated)
- Syncing the repo source to match the running deployed version
- Adding a new enforcement feature (DOGFOOD auto-deploy, extended skills gate)
- Fixing a doctor check that falsely flags a valid state

**Damage (revert):**
- Gutting the MCP server enforcement code
- Relaxing the skills gate (ALL_TOOLS → WRITE_TOOLS only)
- Removing orchestrator-only path protections
- Adding `--no-verify` bypass capabilities
- Removing DOGFOOD auto-remediation

### Phase 5: Produce Report

Structured report format:

```markdown
## Batch Review: <description>

| # | Commit | Author | Changed Files | Enforcement Impact | Verdict |
|---|--------|--------|---------------|-------------------|---------|
| 1 | abc123 | Moses | pre-commit-score (1 line) | Fixed dead-code guard — STAGED_FILES was empty | ✅ Keep |
| 2 | def456 | Moses | loop-gov-mcp.py (1786→102) | Gutted MCP server — all tools stripped | 🔴 Revert |
| 3 | ghi789 | You | SOUL.md template | User's own commit | ⏭️ Skip |

**Summary:**
- **N commits total:** X user, Y agent, Z mixed
- **N enforcement commits:** X fix, Y damage
- **N orchestrator-only violations:** X by non-orch agents
- **Recommended action:** revert A, B, C; keep D, E, F
```

## Communication Protocol: Present Before Acting

When a diagnostic tool (doctor, commit review, system scan) produces findings:

1. **Compile the findings** into a structured summary
2. **Present to the user** — list what was found, severity, and options
3. **Wait for direction** before fixing — the user may want a specific subset reverted, or may have different priorities
4. **Only then act** — fix or revert as instructed

**Anti-pattern:** Diving into fixes without first showing the findings. The user's "what are you doing?" is the signal you skipped this step. If the user has to stop you to ask "what are you doing?", stop, summarize your findings, and wait for direction.

## Phase 6: Execute the Rollback

After the review, when the user directs you to revert: see `references/revert-execution-protected-branch.md` for the protected-branch revert technique (squash revert commits through the pre-commit hook), AGENT_ID sourcing, and the full hook pipeline.

## Pitfalls

### AGENT_NAME from wrong source

When identifying the agent running the review, use the authoritative source:

```bash
grep ^AGENT_NAME ~/.hermes-cortex/cortex-bus.conf | cut -d= -f2
```

Do NOT use `hostname`, `git config user.name`, or `$(whoami)`. The `cortex-bus.conf` file is the single source of truth for agent identity. Every bus message, health report, and registry entry uses this name.

### Git log direction: newest first

`git log` shows newest commits first. When examining a range:

```bash
# Check the actual chronological order
git log --reverse HEAD~N..HEAD

# The oldest commit in a range is the base of the diff
git diff --stat HEAD~N..HEAD   # all changes between
```

### Two commit authors per commit (Author vs Committer)

Git stores two identities — Author (who wrote) and Committer (who pushed). When agents share git config, both fields show the same identity even from different machines. Use:

```bash
git log -1 --format="Author: %an <%ae>%nCommitter: %cn <%ce>"
```

If both are the same, the commit could have come from any machine using that git identity. Cross-reference with push timestamps or SSH keys.
