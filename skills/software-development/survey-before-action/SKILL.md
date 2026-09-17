---
name: survey-before-action
version: 2.1.0
category: software-development
description: >-
  Mandatory pre-flight checklist before creating or modifying any file.
  Prevents redundant work by systematically checking for existing resources
  first. Includes repo-specific pre-flight (git search, Hermes boundary,
  deploy verification — formerly cortex-preflight).
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
aliases:
  - cortex-preflight
related_skills: [change-checklist, skills_list, cron-job-management, agent-fundamentals]
---

# Survey Before Action

Mandatory pre-flight for every file create/modify. Run BEFORE writing any file, adding a cron, creating a skill, or modifying an existing resource.

## Phase 0a: Load Domain Skills (operation × extension)

The 7 always-skills teach HOW to work; domain skills teach WHAT the craft requires. For the first file you create/modify, load every matching skill on BOTH axes:

**Operation axis (strongest):**

| Doing this | Load |
|---|---|
| Cron | `cron-job-management`, `cron-format-standard` |
| Shell script | `shell-scripting` |
| Deploy/install script | `shell-scripting`, `server-administration` |
| nginx | `nginx-web-app-deployment` (security → `nginx-security-pipeline`) |
| Docker/compose | `docker-management`, `env-aware-compose-wrapper` |
| Web app service | `nginx-web-app-deployment`, `prevent-crash-looping` |
| Tests | `test-driven-development` |
| Debugging | `root-cause-debugging` |
| Code review/refactor | `data-structure-efficiency-review` |
| Performance | `linux-performance-diagnostics` |
| Cross-agent feature | `cross-agent-design` |
| Install packages | `package-security` |
| Create skill | `hermes-agent-skill-authoring`, `pii-scrubbing` |
| Documentation | `documentation-auditing`, `doc-freshness` |
| Security change | `linux-server-hardening`, `security-audit` |
| CI/CD | `ci-cd-pipeline` |
| MCP server | `mcp-server-building` |
| SSH/auth/credential | `secure-credential-handling` |

**Extension axis (fallback):** `.sh`/`.bash` → `shell-scripting`; `.py` module → `codebase-design`; `.py` one-shot → `error-handling`; nginx `.conf` → `nginx-web-app-deployment`; Docker yaml → `docker-management`; `.md` → `documentation-auditing`; Makefile → `project-run-scripts`; `.env` → `pii-scrubbing`, `secure-credential-handling`.

**Discovery fallback (always):** `skills_list(category="devops")` + `skills_list(category="software-development")`, and load any `related_skills` a loaded skill names. A skill you never load can never save you.

This runs after loading always-skills + classifying, but BEFORE `begin_change` — you can't know what to lock before you know the domain.

## 1. Search for existing resources

Batch independent searches:

```
search_files(pattern="<keywords>", path="~/hermes-cortex/ops/scripts/", target="files")
search_files(pattern="<keywords>", path="~/.hermes-cortex/scripts/", target="files")
skills_list()
cronjob(action="list")
```

## 2. Examine & decide
| Covers | Action |
|--------|--------|
| 100% | Use as-is |
| 80%+ | Patch the existing tool |
| 50–80% | Refactor or extend |
| <50% | Create new; document why in commit |

## 3. Before deleting/renaming

- Deletion approval — present the plan (what, why zero-consumer, expected gain) and wait for confirmation before rm/git rm.
- Make old names discoverable — add aliases:/tags: (skills), # Formerly known as comment (scripts), deprecation note (docs), both names in commit message.
- Verify target exists — read_file/search_files the exact path before patch/write_file; a nonexistent path silently fails.

## Repo-Specific Pre-Flight (formerly cortex-preflight)

1. Check git for missing files — search_files() scans disk only; a file may exist in git but not deployed. git show HEAD:<path>; deploy with cortex-update.sh.
2. Governance files — orchestrators only — hooks, enforcer plugin, skills: fix the REPO SOURCE in ~/hermes-cortex/ first, commit/push, then cortex-update.sh. A fix to the deployed copy is overwritten on next update.
3. Hermes boundary — in ~/hermes-cortex/ → ours; in ~/.hermes/ AND repo skills/ → edit repo copy + deploy; in ~/.hermes/ NOT in repo → Hermes default, don't touch; ~/.hermes-cortex/state/* and ~/.hermes/config.yaml → live config, edit directly.
4. Verify deployed == repo — grep -n "register.*<script>" cortex-update.sh; deploy if missing.
5. Agent type — orchestrator (Moses/Esther): fleet/bus/skill-lifecycle; server-agent (Joseph/Kustos/Gisu): local maintenance; dev-agent (Titus): local reports, push-only bus.
6. Stale deploy references — before rename/removal, grep every location (ops/scripts/, ops/install/, cortex_doctor/, hooks/, config/, state/, manage/). A rename touches updater, install arrays, doctor, check-system, service-recovery, cron-schedules.
7. Foreign working-tree check — git status; a peer's in-flight edits block the pre-push gate. Never stash/clean a peer's work.

## Deployment Pitfalls (cortex-update.sh side effects)

1. SOURCE header breaks checksums — deployed .sh/.py get a # SOURCE: header; use the doctor's _content_md5() (strips header), never raw _md5().
2. Lock purge — cortex-update removes stale locks (>1h TTL). Re-acquire with begin_change(); score PENDING cycles from the purged lock first.
3. Skills marker survives deploy — write tools keep working after cortex-update.
4. Hook symlinks — deployed hooks are symlinks to scripts/ sources; a file copy drifts and the doctor flags it.
5. PENDING cycles accumulate — score all PENDING cycles before end_change().

## Critical rules

- Search ops/scripts/ first; check skills_list() and cronjob list before creating.
- Never trust a single zero-result search_files — verify with ls/find/git ls-tree/git log.
- Never register user-owned files in the deploy map (register() overwrites on drift). Memory files are Hermes-owned and must NEVER be registered; cortex-update fails closed on /memories/ and ~/.hermes/ targets.

## Post-Action Audit (before end_change)

- Stale communications — after rename/delete, check pending inbox messages; correct any that reference stale paths.
- Decide whether to share — script → ops/scripts/ + register; skill → skills/<cat>/<name>/; cron pattern → AGENTS.md/cron-schedules; machine-specific → keep private. Default: share.
- Guardrail — if this responded to a mistake, did you add a guardrail that prevents recurrence, and is it enforceable/tested?
- Test before shipping — exercise the actual changed code path, not just the diff: run the script, commit through the RUNNING hook, verify the RUNTIME copy changed.

## Repo-Wide Stale-Artifact Audit (comprehensive reviews only)
1. Structural integrity (README vs reality, VERSION, DOCS-INDEX) · 2. Git-tracked build artifacts (__pycache__, .pyc) · 3. .gitignore accuracy · 4. Skill duplicates (find . -name SKILL.md ... | uniq -d) · 5. Doc-vs-reality (compose links, counts, paths) · 6. Test paths (stale src/, deploy/) · 7. Mid-survey user requests → tag follow-up, finish current step.
