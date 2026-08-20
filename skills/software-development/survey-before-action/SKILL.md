---
name: survey-before-action
version: 2.0.0
category: software-development
description: >-
  Mandatory pre-flight checklist before creating or modifying any file.
  Prevents redundant work by systematically checking for existing resources
  first. Includes repo-specific pre-flight (git search, Hermes boundary,
  deploy verification — formerly cortex-preflight) and a full-repo
  stale-artifact audit pattern.
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
aliases:
  - cortex-preflight
related_skills: [change-checklist, skills_list, cron-job-management, agent-fundamentals]
---

# Survey Before Action

**Mandatory pre-flight for every file create/modify operation.**

Run this BEFORE writing any file, adding a cron, creating a skill, or modifying any existing resource. Do not skip, batch, or defer.

## Survey

### Phase 0a: Load Domain Skills for the Operation Type

**Before searching existing resources, load domain knowledge for what you're about to build.** The 8 always-skills (task-start, agent-flow, survey-before-action, etc.) teach you HOW to work. Domain skills teach you WHAT the craft requires — pitfalls, portability, conventions, gotchas.

Without domain skills, agents make preventable mistakes: writing `.sh` files with bash portability bugs, creating crons with wrong output formats, patching nginx with macOS paths on Linux.

**The rule: for the first file you create or modify, check both axes — operation and extension — and load EVERY matching skill.**

#### Operation-Axis Triggers (strongest signal)

| If you're doing this ... | Load these skills |
|---|---|
| Creating or fixing a cron | `cron-job-management`, `cron-format-standard` |
| Writing a shell script (any purpose) | `shell-scripting` |
| Writing a deployment / install script | `shell-scripting`, `survey-before-action`, `server-administration` |
| Configuring nginx | `nginx-web-app-deployment` (or `nginx-security-pipeline` if security-focused) |
| Configuring Docker / compose | `docker-management`, `env-aware-compose-wrapper` |
| Building a web app service | `nginx-web-app-deployment`, `prevent-crash-looping` |
| Writing tests (any language) | `test-driven-development` |
| Debugging a failure | `root-cause-debugging` (or `systematic-debugging`) |
| Performance diagnosis | `linux-performance-diagnostics` |
| Cross-agent feature / protocol | `cross-agent-design` |
| Installing packages | `package-security` |
| Creating a skill | `hermes-agent-skill-authoring`, `pii-scrubbing` |
| Writing documentation | `documentation-auditing`, `doc-freshness` |
| System security change | `linux-server-hardening`, `security-audit` |
| Deploying Langfuse | `langfuse-self-hosted` |
| Configuring Ollama | `ollama-setup` |
| Setting up CI/CD | `ci-cd-pipeline` |
| Building MCP server | `mcp-server-building` |
| SSH / auth / credential change | `secure-credential-handling` |

#### Extension-Axis Triggers (secondary, when operation isn't specialized)

If the operation isn't in the table above, fall back to file extension:

| File extension | Load these skills |
|---|---|
| `.sh` / `.bash` | `shell-scripting` |
| `.py` (module-level, not one-shot) | `codebase-design`, `python-debugpy` |
| `.py` (one-shot script) | `error-handling` |
| `.conf` (nginx) | `nginx-web-app-deployment` |
| `.yaml` / `.yml` (Docker) | `docker-management` |
| `.yaml` / `.yml` (general) | `skills_list` fallback |
| `.md` | `documentation-auditing` |
| Makefile | `project-run-scripts` |
| `.json` | `skills_list` fallback — no dedicated skill |
| `.sql` | `skills_list` fallback — known gap, no dedicated skill |
| `.toml` | `skills_list` fallback — known gap |
| `.env` | `pii-scrubbing`, `secure-credential-handling` |

#### Discovery Fallback — Always Run

After loading the matched skills, always run a discovery sweep for skills you didn't know existed:

```python
# Category derived from the primary file type or operation domain
# e.g. 'devops' for .sh / cron / docker, 'software-development' for .py
skills_list(category="devops")
skills_list(category="software-development")
# If you load a skill that references others, load those too
related = skill_view(name="X").related_skills or []
for name in related:
    skill_view(name=name)
```

This catches the skills the mapping table author didn't think of. **A skill you never load can never save you from a mistake.**

#### When to Load

This Phase 0a runs AFTER you've loaded the 8 always-skills (task-start, agent-flow, etc.) and AFTER you've classified the task with agent-flow (Step 5), but BEFORE you open a governance lock (begin_change). It supplements the "on-task skills" from the manifest.

Sequence:
1. ✅ Always skills loaded (task-start)
2. ✅ Task classified (agent-flow)
3. ✅ Domain skills loaded ← **you are here**
4. → begin_change (governance lock)
5. → Search existing resources (Phase 1)

**Why before begin_change:** You cannot know what to lock if you don't know what domain knowledge you need. Loading domain skills first means your first change is informed.

### 1. Search for existing resources

Search these in order. Batch independent searches together.

```
search_files(pattern="<keywords>", path="~/hermes-cortex/ops/scripts/", target="files")
search_files(pattern="<keywords>", path="~/.hermes-cortex/scripts/", target="files")
skills_list()
cronjob(action="list")
```

**Keywords:** function name, tool name, purpose (e.g. "audit", "health", "failure")

### 2. Examine what exists

If a candidate match is found, read it before deciding. Assess:
- Does it do some or all of what I need?
- Can I add a flag/parameter to extend it?
- Is it in the right location or needs moving?

### 3. Decision

| If ... | Then ... |
|--------|----------|
| Covers 100% | Use as-is |
| Covers 80%+ with small patch | Patch the existing tool |
| Covers 50-80% | Refactor or extend |
| Covers <50% | Create new. Document why in commit. |

### 4. Creating something new anyway

Document in commit why existing resources don't fit.

### 4b. User approval for deletions

If your plan includes deleting files or directories, present the deletion plan for approval BEFORE executing. Show what, why safe to remove (zero consumers, stale duplicate, etc.), and expected improvement. Wait for explicit confirmation before `git rm` or `rm -rf`.

### 4c. Make old names discoverable before deletion

Before deleting a renamed/merged artifact, ensure the surviving artifact makes the old name findable:
- **Skills:** add `aliases: [old-name]` or `tags: [old-name]` in frontmatter
- **Scripts/tools:** add `# Formerly known as` comment or `--compat` flag
- **Docs:** add deprecation note at the top (e.g. `> Moved to [new-path](new-path.md)`)
- **Git history:** mention both names in commit message

**Why:** A deletion without discoverability orphans every inbox message, cron config, and agent reference that used the old name.

### 4d. Guardrail: verify target exists before editing

Before calling `patch()`, `write_file()`, or any tool that modifies a file, confirm the exact target path exists with `read_file()` or `search_files(target="files")` first. Patching a nonexistent path silently fails — the edit never lands. Always verify with a second method. `search_files(target="files")` matches basenames only, not directory names.

## Repo-Specific Pre-Flight (formerly cortex-preflight, merged 2026-08-20)

Run these after the generic survey above, before writing code — they are
specific to the Hermes Cortex repo and its deployment model.

### 1. Check git for missing files

`search_files()` only scans disk. If it finds nothing, the file may still
exist in git (committed but not deployed):

```bash
cd ~/hermes-cortex
git log --oneline --all -- "**/<pattern>*"   # search git history
git show HEAD:<path-to-file>                  # view file in git but not disk
```

**Common scenario:** script exists in repo (`ops/scripts/manage/foo.py`)
but was never deployed to `~/.hermes-cortex/scripts/foo.py`. Running
`cortex-update.sh` fixes this.

### 2. GOVERNANCE FILE WORKFLOW — ORCHESTRATORS ONLY

Non-orchestrators: stop here for these files — send an inbox message to
`inbox_orchestrator` requesting the change. If you ARE an orchestrator
(Moses, Esther): hooks, enforcer plugin, and skills follow this rule:

1. Fix the **REPO SOURCE first** in `~/hermes-cortex/` — never the deployed copy
2. Commit, push, then run `cortex-update.sh` to deploy
3. A fix applied to the deployed copy WILL be overwritten on next update

Specific files (always repo source, never deployed copy): `~/.hermes/plugins/governance-enforcer/__init__.py`, `~/.hermes-cortex/scripts/pre-commit-score`, `~/.hermes-cortex/hooks/*` (symlinks), `~/.hermes/skills/<cat>/<name>/SKILL.md`, all files with a `register()` entry in `cortex-update.sh`.

### 3. Hermes boundary check

| File location | Action |
|---------------|--------|
| In `~/hermes-cortex/` | ✅ Ours — modify freely |
| In `~/.hermes/` AND in repo `skills/` | ✅ Ours — modify the repo copy, deploy |
| In `~/.hermes/` but NOT in repo | ❌ Hermes default — do NOT touch |
| In `~/.hermes-cortex/state/*` | ✅ Live config — modify directly |
| In `~/.hermes/config.yaml` | ✅ Live config — modify directly |

To extend a Hermes default skill, create a **supporting skill** in the repo
(see `file-ownership-boundaries` skill) instead of editing the default.

### 4. Verify deployed copies match repo

A source change is not deployed until `cortex-update.sh` runs:

```bash
grep -n "register.*<script-name>" ~/hermes-cortex/ops/scripts/cortex-update.sh
ls -la ~/.hermes-cortex/scripts/<script-name>
bash ~/hermes-cortex/ops/scripts/cortex-update.sh   # if missing
```

### 5. Check what agent type you are

| Agent type | Can do |
|------------|--------|
| orchestrator (Moses, Esther) | Fleet dispatch, bus operations, skill lifecycle |
| server-agent (Joseph, Kustos, Gisu) | Local maintenance, health reports |
| dev-agent (Titus) | Local reports, push-only bus |

### 6. Check for stale deploy references — EVERY deploy location

Before renaming or removing a file, search every location that could
reference the old name (not just the obvious ones):

```bash
for dir in ~/hermes-cortex/ops/scripts/ ~/hermes-cortex/ops/install/ \
  ~/hermes-cortex/ops/scripts/cortex_doctor/ ~/hermes-cortex/hooks/ \
  ~/hermes-cortex/.hermes-cortex/ ~/hermes-cortex/config/ \
  ~/hermes-cortex/state/; do
  [ -d "$dir" ] && grep -rn "<old-name>" "$dir" 2>/dev/null
done
```

**Easy-to-forget dirs:** `cortex_doctor/` (checks, expected cron lists,
remediation hints), `hooks/`, `config/` (repo-owners.yaml, skills
manifests), `state/` (seen-file tracking), `manage/` (subdirectory scripts).

A single rename can touch: `cortex-update.sh` (register + unregister),
install scripts (create + uninstall arrays), `cortex-doctor/checks.py`
(remediation hints), `check-system.sh` (service lists),
`service-recovery.py` (service labels), and `cron-schedules.md`.

### 7. Verify other agents won't be affected

```bash
grep -rn "<changed-path>" ~/hermes-cortex/profiles/
grep -rn "<changed-protocol>" ~/hermes-cortex/AGENTS.md
```

## Deployment Pitfalls — cortex-update.sh Side Effects

Account for each before and after deploy:

1. **SOURCE header breaks checksums.** `cortex-update.sh` adds a `# SOURCE:`
   header below the shebang to every deployed `.sh`/`.py`. Raw MD5 between
   repo and deployed ALWAYS differs. Use the doctor's `_content_md5()`
   (strips header) on deployed paths — never `_md5()`.
2. **Lock cleanup.** cortex-update removes `.governance-*.json` locks whose
   heartbeat exceeded TTL (>1h) plus legacy v1 locks. A fresh session-scoped
   v2 lock survives. If your lock is gone after deploy, re-acquire with
   `begin_change()` — and score any PENDING cycles from the purged lock first.
3. **Skills-loaded marker survives deploys.** Per-session marker files at
   `state/skills-loaded/<session-id>` survive the enforcer plugin reload —
   write tools keep working after cortex-update. (The old shared-marker race
   is gone since 2026-08-01.)
4. **Hook symlinks prevent drift.** Deployed hooks (`~/.hermes-cortex/hooks/`)
   are absolute symlinks to `~/.hermes-cortex/scripts/` sources. If a hook is
   a file copy instead of a symlink, it drifts and the doctor flags it. The
   repo `.hermes-cortex/hooks/` tracks docs only, not deployables.
5. **PENDING cycles accumulate.** Every `begin_change()` creates a cycle;
   when cortex-update purges the lock and you re-acquire, old cycles stay
   PENDING. Score ALL PENDING cycles (`feedback_accept`/`feedback_override`)
   before `end_change()` or the doctor reports a governance leak.

## Critical rules

- **Search ops/scripts/ first** — canonical location for installed scripts
- **Check skills_list()** — if a skill already covers the workflow, use it
- **Check cronjob list** — existing cron patterns may already solve the problem
- **Never trust a single zero-result `search_files`.** When you get 0 results, verify with `ls`, `find`, `git ls-tree`, or `git log` before concluding the resource doesn't exist.
- **Never register user-owned files in the deploy map.** A `register()` entry in `cortex-update.sh` makes a file a deploy target — it is overwritten whenever content differs. That is right for repo-managed files, destructive for files an agent personalizes (memory, user config). Memory (`MEMORY.md`/`USER.md`) is Hermes-owned and must NEVER be registered (2026-08-05: a memory seed register clobbered live memory 7× in a day; the doctor then FAILed on the healthy personalized state and suggested the destructive resync). `cortex-update.sh` now fails CLOSED on any target under `/memories/` or `~/.hermes/` — the guard is physical, not a convention.
- **If no match found:** note it mentally. Do not skip this step next time.

---

## Post-Action Audit

**Mandatory post-flight before calling end_change().**

### 5. Search for stale communications

After modifying, deleting, or renaming files other agents reference, check pending outbound messages with `mcp_agent_inbox_inbox_read(unread_only=True)`. If any reference now-stale paths or instructions, send a correction before releasing the governance lock.

### 6. Decide whether to share

| I created/modified ... | I should put it in ... |
|------------------------|------------------------|
| A script | ops/scripts/ + register in cortex-update.sh |
| A skill | skills/<category>/<name>/ |
| A cron pattern | AGENTS.md or cron-schedules.md |
| A workflow/technique | Save as a skill or reference |
| Machine/user specific | Keep private |

Default posture: share.

### 7. Verify the guardrail

If this work responded to a mistake: did you implement a guardrail that prevents recurrence? Is it enforceable? Test it catches the same failure. If any answer is no, the loop isn't closed.

### 8. Test before shipping

**Every change must be verified end-to-end before pushing to main.** Verification means exercising the actual changed code path — not just staring at the diff.

| What changed | Verification required |
|-------------|----------------------|
| install-crons.sh cron | Run test cron via CLI, confirm registration, clean up |
| Shell script | `bash -n <file>` + live test of changed branch |
| Python script | Run with expected args, check output and exit code |
| Cron definition | Create test cron, verify in list, remove |
| Pre-commit/git hook | Commit through the RUNNING hook, not the repo copy |
| Any file with runtime copy | Verify the RUNTIME copy changed — not just the repo source |

The check before git push: "Did I actually run the changed code path?" If only looked — stop. Run it.

**Failures this catches:**
- Escaped `$HOME` in workdir → literal string passed, CLI rejects silently
- Missing script at destination → cron creates but fails every tick
- Absolute path that works on one machine but not others
- **Repo source changed but running copy stale** — editing `.hermes-cortex/hooks/pre-commit` while `core.hooksPath` points to `~/.hermes-cortex/hooks/` where the old version still runs

### 9. Audit post-push communications

After pushing to main, verify outbound messages match the deployed state. If you described a feature as "available" but it's not on main at the receiver's pulled commit, send a correction.

## Companion tools

- `scripts/agents-doc-audit.py` — prune accumulated doc refs after surveys
- `references/hook-deployment-audit.md` — runtime-vs-repo path mistakes
- `references/testing-deployable-scripts.md` — detailed test patterns by type

---

## Appendix: Repo-Wide Stale-Artifact Audit

When the task is a comprehensive repo review, the per-operation checklist above is too narrow. Run this instead:

1. **Structural integrity** — README vs Reality, VERSION consistency, DOCS-INDEX stale paths
2. **Git-tracked build artifacts** — `git ls-files | grep -E '(__pycache__|\\.pyc$)'` 
3. **.gitignore accuracy** — stale negated patterns for deleted files; missing ignores for artifacts found
4. **Skill duplicates** — `find . -name SKILL.md -exec sh -c 'basename $(dirname $_)' \\; | sort | uniq -d`
5. **Doc-vs-reality** — docker-compose links, script counts, cron counts, alleged file paths
6. **Test paths** — search tests for stale source paths (`src/`, `deploy/`, etc.)
7. **Mid-survey user requests** — tag as follow-up, finish current step, return immediately

## Why this exists

Created after building `check-agents-dot-md.py` when `agents-doc-audit.py` already existed. A 15-second search would have prevented the redundant work.

Phase 0a was added per Luke's directive after Esther identified the gap: agents load always-skills (governance/process) but skip domain skills (craft knowledge). Without domain skills, agents make preventable mistakes — bash portability bugs, wrong cron output formats, path conventions for the wrong OS.
