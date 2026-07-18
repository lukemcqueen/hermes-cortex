# Contributing to Hermes Cortex

> **Written for agents, by agents.** This guide tells any Hermes Cortex agent how
> to make changes, add features, fix bugs, and improve the shared repo so every
> agent benefits.

## Two Hard Rules (Non-Negotiable)

> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change REQUIRES: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. No exceptions. If `end_change` rejects, confess and force-clear — never silently skip the loop. The MCP server blocks write tools without an active lock — this is enforced at the tool level, not optional.

> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo — template files, skills, scripts, docs, config patterns. Not just your local profile. The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

## Overview

**Hermes Cortex** is a public GitHub repo (`fleet-operator/hermes-cortex`) containing:

- **Source scripts** in `ops/scripts/` — watchdogs, installers, utilities
- **Canonical skills** in `skills/` — organized by domain
- **Documentation** in `docs/` — guides, templates, troubleshooting
- **Deployment configs** in `deploy/` — nginx, Docker, patches
- **Service/agent infra** in `ops/services/` (agent-bus, dashboard) and `mcp-servers/` (agent-bus-mcp, loop-governance)

When you make an improvement here, every agent running `cortex-update.sh` gets it
on their next pull. This is the force multiplier.

## Before You Start — Load These Skills

These skills contain the exact workflows, conventions, and standards for this repo.
Load them at the start of any contribution session:

| Skill | What it covers | Load when ... |
|-------|---------------|---------------|
| `survey-before-action` | Pre-flight checklist — search existing resources before creating new ones | **Always** — before any file create/modify |
| `engineering-approach` | Communication standards, CLI design, version management | **Always** — communication with the user |
| `public-contribution` | Decision tree for what to share, genericization patterns, commit workflow | When deciding what belongs in the public repo |
| `repo-organization` | Canonical directory structure, naming conventions, consolidation rules | When deciding where a file goes |
| `hermes-agent-skill-authoring` | In-repo SKILL.md format, frontmatter requirements, quality checks | When writing/editing a skill in `skills/` |
| `loop-governance` | Scoring workflow, cycle management, governance DB | **Always** — until the MCP server auto-loads it |
| `two-hard-rules` | Both hard rules (loop governance + share improvements) | **Always** — reinforcement |

## The Change Workflow

### Step 1: Survey Existing Resources

Before writing anything new, search for existing tools:

```bash
# Search scripts
search_files(pattern="<topic>", path="~/hermes-cortex/ops/scripts/", target="files")
search_files(pattern="<topic>", path="~/.hermes-cortex/scripts/", target="files")

# Search skills
skills_list()

# Search existing cron jobs
cronjob(action="list")

# Search documentation
search_files(pattern="<topic>", path="~/hermes-cortex/docs/", target="content")
search_files(pattern="<topic>", path="~/hermes-cortex/AGENTS.md", target="content")
search_files(pattern="<topic>", path="~/hermes-cortex/README.md", target="content")
```

If something exists that covers 80%+ of the need: **patch it, don't replace it.**
Every new file is a tax on the whole system. Only create new when there's a
documented reason existing resources don't fit.

**Corollary — check for naming collisions:**
```bash
search_files(target="files", path="~/hermes-cortex", pattern="<proposed-name>*")
```
If a file with your proposed name already exists in a different location, you may
be duplicating functionality. Investigate before writing.

### Step 2: Open Governance Lock

```python
mcp_loop_governance_begin_change(task_id="<short-description>", description="<what this does>")
```

This opens a governance lock AND creates a pending cycle in the loop-governance
DB. The MCP server/enforcer blocks write tools without an active lock.

### Step 3: Read Before Edit

Always read the current state of any file before modifying it:

```python
read_file(path="path/to/file")
```

Never edit a file based on assumptions about its content. If you wrote it in
this same turn, you can skip this step.

### Step 4: Make the Change

| What you're doing | Tool | Notes |
|-------------------|------|-------|
| New file | `write_file` | Creates dirs automatically, runs syntax checks |
| Small edit (find-and-replace) | `patch` (mode=replace) | Fuzzy matching, auto-syntax-check, returns diff |
| Bulk multi-file change | `patch` (mode=patch) | V4A format — `*** Begin Patch`, `@@ context @@` |
| Move/rename file | Terminal: `git mv` | Update all references in the same commit |
| Delete file | Terminal: `git rm` | Remove all references and MAP entries first |

#### File Placement Rules

| Type | Home | Also register in |
|------|------|-----------------|
| Source script | `ops/scripts/<kebab-name>.py` or `.sh` | `cortex-update.sh` MAP (see MAP format below) |
|| Canonical skill | `skills/<category>/<name>/SKILL.md` | `docs/SKILLS-MANIFEST.md` |
| Documentation | `docs/<slug>.md` | `docs/DOCS-INDEX.md` |
| Config template | `docs/templates/<name>` | — |
| Nginx config | `ops/install/deploy/nginx/<name>.conf` | — |
| Docker config | `ops/install/deploy/<name>.yml` | — |
| Test | `tests/<category>/test_<name>.py` | — |

#### Service Layer Policy — Critical

All Hermes Cortex agent services MUST run at user level:

| Platform | Agent Services | System Services (remain) |
|----------|---------------|------------------------|
| **Linux** | `~/.config/systemd/user/` (`systemctl --user`) | docker, nginx, fail2ban |
| **macOS** | `~/Library/LaunchAgents/` (`launchctl load`) | docker, nginx, fail2ban |

**When adding a new service or daemon:**
- If it runs as the user and doesn't need root → user-level only
- If it needs root (Docker, nginx, fail2ban) → system-level only
- **Never both.** Duplicate layers cause restart loops, port conflicts, and silent failures

**Correct unit file patterns:**
- Linux: `WantedBy=default.target` (NOT `multi-user.target`)
- macOS: `KeepAlive` + `RunAtLoad` in LaunchAgent (NOT LaunchDaemon)

Full reasoning: [`docs/service-layer-decision.md`](docs/service-layer-decision.md)
Platform guides: [`docs/linux-service-layer.md`](docs/linux-service-layer.md), [`docs/macos-service-layer.md`](docs/macos-service-layer.md)

#### Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Scripts | kebab-case | `system-alert-watchdog.py` |
| Skill directories | kebab-case, matches `name:` in SKILL.md | `survey-before-action/` |
| Cron jobs (LLM-driven) | `agent-*` prefix | `agent-auto-remediate` |
| Cron jobs (script-only) | No prefix | `system-alert-watchdog` |
| Python modules | snake_case (PEP 8) | `loop_scorer.py` |
| Documentation | kebab-case | `git-enforcement.md` |

#### Cortex-Update.sh MAP Registration

If you add a script that needs deployment to `~/.hermes-cortex/scripts/`, register
it in `cortex-update.sh`:

```bash
# Format:
register "ops/scripts/your-script.py" \
  "${HERMES_HOME}/scripts/your-script.py"
```

The MAP is at the top of `cortex-update.sh`, after the `register()` function.
Entries are grouped by destination directory. Insert your entry in the correct
alphabetical position within its group.

If the script needs a service restart or symlink, add a 3rd and 4th field:

```bash
register "ops/scripts/my-daemon.py" \
  "${HERMES_HOME}/scripts/my-daemon.py" \
  "my-daemon" \
  "systemctl --user restart my-daemon"
```

### Step 5: Genericize (for Public Repo)

Before committing, scrub any PII from your changes:

| Private → | Public placeholder |
|-----------|-------------------|
| `your-domain.com` | `your-domain.com` (domain in example) or `example.com` |
| `your-username` | `your-username` |
| `/home/your-user/...` | `$HOME/...` or `/path/to/app` |
| `real-server-name` | `your-server` |
| Port `13003` | `EXTERNAL_PORT` |
| Hardcoded API keys | `$ENV_VAR` placeholders |
| Real IP addresses | `10.0.0.1` (RFC 1918) or `your-server-ip` |
| Secret tokens | `your-token-here` |

**Golden rule:** If a file contains your real domain, real paths, or real
credentials, it does not belong in the public repo without genericization.

### Step 5b: Documentation Audit — Mandatory

**Before committing, audit whether your change needs documentation updates.**

You must answer **NO** to ALL of these before proceeding:

| Question | If YES → | 
|----------|----------|
| | Did you create or modify a **file** in `ops/scripts/`, `skills/`, or `deploy/`? | Update `cortex-update.sh` MAP or `docs/SKILLS-MANIFEST.md` |
| Did you create or modify a **documentation file** (any `.md` in `docs/`)? | Update `docs/DOCS-INDEX.md` with new/changed entry |
| Did you add a **new configuration template**? | Add to `docs/DOCS-INDEX.md` under Templates |
| Did you add a **service or daemon**? | Update `docs/linux-service-layer.md` or `docs/macos-service-layer.md` fleet service map |
| Did you change how a **public command or API** works? | Update the relevant documentation file + docstring |
| Did you change a **cron schedule or script path**? | Update `docs/cron-job-recipes.md` or `docs/fleet-reference.md` |
| Did you add a **new environment variable**? | Update `docs/env-vars.md` |
| Did your change affect **agent behavior or session startup**? | Check if `AGENTS.md` or `README.md` needs updating |
| Is your change significant enough that **another agent would benefit** from knowing about it? | Add a brief note to `docs/whats-new.md` or the relevant guide |

**If any answer is YES → update the corresponding doc before committing.**

The verification is simple:
```bash
# After staging all files, check if docs/ or templates/ changed
git diff --cached --name-only | grep -E '^(docs|skills|ops/install/deploy/nginx)/' > /tmp/dirty_docs.txt
# If non-empty, run the table above against each changed file
```

**Golden rule:** A feature doesn't exist until its documentation is in the same commit.

### Step 6: Test Before Shipping

**Every change to a script, config, or installer must be verified end-to-end**
**before pushing to main.**

| What changed | Verification required |
|-------------|----------------------|
| `install-crons.sh` cron config | Run a test cron create with the actual CLI, confirm it registers, clean up |
| Shell script logic | `bash -n <file>` + live test exercising the changed branch |
| Python script | Run it with expected arguments, check stdout + stderr + exit code |
| Cron definition | `hermes cron create --name test-<x> ...` → verify in `cronjob list` → remove test job |
| Config file | Run the tool that reads it and confirm the expected behavior |
| Nginx config | `nginx -t` to validate syntax |

**The check before `git push`:** Did you actually run the changed code path, or
did you only stare at the diff? If only looked — stop. Go run it.

### Step 7: Commit

```bash
cd ~/hermes-cortex
git add -A
```

Commit message format:
```
<type>(<scope>): <imperative description>

<optional body — why this change exists, not what it does>
```

| Type | When |
|------|------|
| `feat` | New script, skill, doc, or config |
| `fix` | Bug fix |
| `docs` | Documentation-only change |
| `refactor` | Restructure without behavior change |
| `chore` | Maintenance, tooling, gitignore, CI |
| `test` | Test-only changes |

Examples:
```
feat(scripts): add system-alert-watchdog for disk/CPU monitoring
fix(crons): correct cron workdir escaping for $HOME
docs(contributing): add CONTRIBUTING.md for agent contributions
refactor(cortex-update): extract MAP registration into register()
```

**Always commit through `git commit` in terminal** (the pre-commit hook runs
governance scoring). Do NOT use `write_file` + `patch` to bypass git — this
repo is the source of truth, and git is how changes are distributed.

### Step 8: Push

```bash
git push
```

The pre-push hook verifies your local `main` isn't behind `origin/main`. If
it blocks, pull first:

```bash
git pull --rebase
git push
```

Pushing directly to `main` is the standard workflow for agent contributions.
Feature branches are not required — agents work in short cycles and push tested,
single-commit changes.

### Step 9: Verify Post-Push Communications

After pushing, check whether any pending inbox messages to other agents reference
now-stale paths, commands, or instructions:

```python
mcp_agent_inbox_inbox_read(unread_only=True)
```

If you sent instructions describing a feature that's now on `main`, and the
feature exists at the commit the agents will pull — good. If you described a
feature as "available" before it was pushed, send a correction telling agents
to pull first.

### Step 10: Close the Governance Loop

```python
# 1. Find the cycle
mcp_loop_governance_cycle_query(task_id="<your-task-id>")

# 2. Accept feedback (or override if it was wrong)
mcp_loop_governance_feedback_accept(id=N, note="<summary>")

# 3. Release the lock
mcp_loop_governance_end_change(task_id="<your-task-id>")
```

**If `end_change` rejects** (no cycle auto-created for this tool type):
1. **Confess clearly** — "end_change rejected — no cycle auto-created. Force-clearing."
2. `rm -f ~/.hermes-cortex/state/.governance-<repo-slug>.json`
3. Document the missed auto-cycle gap

## What You Can Contribute

### High-Value Contributions

| Contribution | Where it goes | Agent benefit |
|-------------|---------------|---------------|
|| **New canonical skill** | `skills/<category>/<name>/SKILL.md` | Every agent can load your workflow |
| **New script** | `ops/scripts/<name>.py` + MAP in cortex-update.sh | Every agent gets the tool on `cortex-update` |
| **Docs improvement** | `docs/<slug>.md` + DOCS-INDEX.md | Every agent can discover and read it |
| **Bug fix** | Same location as the bug | Every agent stops hitting the same bug |
| **Cron job** | Document in AGENTS.md or as install-crons.sh entry | Shared maintenance automation |
| **Template improvement** | `docs/templates/<name>` | Better starting point for every new install |
| **Tests** | `tests/<category>/test_<name>.py` | Higher confidence for every contributor |
|    **Config improvement** | `ops/install/deploy/nginx/` | Better defaults for every deploy |

### What NOT to Contribute

- Your personal MEMORY.md, USER.md, or SOUL.md (these are per-agent)
- Machine-specific config with real domains/paths (genericize first)
- Session logs or brain content (private)
- Secrets, tokens, or credentials (never)
- Generated output files (`.cron-version`, `*.db`, `__pycache__`)

## Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **Skipping survey-before-action** | Created `check-agents.py` when `agents-doc-audit.py` already exists | Always search first — 15 seconds saves 15 minutes |
| **Forgetting cortex-update.sh MAP** | Script exists in repo but never deploys | Register new scripts in the MAP immediately |
| **Not genericizing PII** | Real domain in public repo | Apply genericization transforms before commit |
| **Skipping end-to-end test** | `$HOME` literal string in cron workdir, cron fails silently | Run the actual CLI to verify before push |
| **Stale bus instructions** | Told another agent to use a path you just renamed | Audit post-push communications (Step 9) |
| **Describing un-pushed features** | Agent tries feature that doesn't exist on their main | "Pull to HEAD first, then this works" |
| **Half-wired abstractions** | Created config file with 0 readers | Wire all consumers in the same commit |
| **Wrong naming** | Skill directory `my-skill` but SKILL.md has `name: My Skill` | Directory name must match `name:` in frontmatter |
| **Forgetting DOCS-INDEX.md / SKILLS-MANIFEST.md** | New doc/skill exists but isn't discoverable | Always update the index |

## Reference: File Map (from cortex-update.sh)

The `cortex-update.sh` MAP defines where files are deployed. When adding a file
that needs to be installed on agent machines, register it here:

| Repo path → | Installed path |
|-------------|---------------|
| `ops/scripts/<name>` | `~/.hermes-cortex/scripts/<name>` |
|| `ops/services/<service>/` files | `~/.hermes-cortex/<service>/` |
| `ops/services/dashboard/` files | `~/.hermes-cortex/dashboard/` |
|| `skills/<category>/<name>/` | `~/.hermes/skills/<category>/<name>/` (via symlink) |
| `core/governance/` files | `~/.hermes-cortex/loop-governance/` |
| `ops/install/deploy/nginx/` files | `~/.hermes-cortex/nginx/` |
| `docs/` | Read from repo (no deployment needed) |
| `install.sh` | `~/.hermes-cortex/install.sh` |

> **Note:** Skills from `skills/` are symlinked during `cortex-update.sh` to
> `~/.hermes/skills/<category>/<name>/`. The skill_loader loads from
> `~/.hermes/skills/` — the symlink makes the repo the source of truth.

## The Spirit of This Document

Hermes Cortex is an open-source community project. Every agent contributing to
it is helping every other agent run better. The standards here exist not to be
bureaucratic, but to ensure that:

- **Every improvement actually arrives** at its destination (MAP registration)
- **Every agent can trust the repo** (tested, genericized, documented)
- **Nothing is duplicated** (survey-before-action)
- **Nothing breaks silently** (end-to-end verification)
- **Nothing is lost** (DOCS-INDEX, SKILLS-MANIFEST, git)

If you're unsure about anything — ask the human (Luke) or send a message via the Agent Bus
to Moses, who maintains the repo and its conventions.
