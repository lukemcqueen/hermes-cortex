# Cortex Path Migration — July 2026: `src/` → `ops/`

## Migration Context

The hermes-cortex repo restructured from a `src/` prefix to an `ops/` prefix for
operational files (scripts, services, offline tools), and `deploy/` was moved
under `ops/install/deploy/`. All path references in deployed cron scripts
(`~/.hermes/scripts/*.sh`, `~/.hermes/scripts/*.py`) needed updating.

## Old → New Mapping (complete)

| Old path | New path | Type |
|----------|----------|------|
| `ops/scripts/` | `ops/scripts/` | Shell scripts, Python scripts |
| `src/mcp-servers/` | `ops/services/` | MCP servers (Python files) |
| `src/offline/` | `ops/offline/` | Offline utilities |
| `src/web-cache/` | `ops/web-cache/` | Web cache modules |
| `src/a2a/` | `ops/services/a2a/` (later deprecated, merged into agent-bus) | Agent card templates |
| `skills/` | `runtime/skills/` | Skill manifests (SKILL.md) |
| `core/governance/` | `core/governance/` | Loop governance tools |
| `deploy/nginx/` | `ops/install/deploy/nginx/` | Nginx configs + scripts |
| `deploy/` (general) | `ops/install/deploy/` | Docker compose, env files |
| `deploy/docker-compose.langfuse.yml` | `ops/install/deploy/docker-compose.langfuse.yml` | Langfuse compose |
| `mcp-servers/venv` | `services/venv` | Virtualenv for MCP servers |

## Reference Files Modified (Python)

| File | Changes | Lines touched |
|------|---------|---------------|
| `remediation-sensor.py` | `"src" / "scripts"` → `"ops" / "scripts"`; git status path; add_issue detail string | 37, 96, 98 |
| `cortex-doctor.py` | `"src" / "mcp-servers"` → `"ops" / "services"`; `"src" / "scripts"` → `"ops" / "scripts"` (3 occurrences) | 59, 145, 1171, 1195 |
| `hermes_paths.py` | Docstrings: `src/offline/` → `ops/offline/`, `src/web-cache/` → `ops/web-cache/`, `src/mcp-servers/` → `ops/services/`; inline comment | 6, 23, 29 |
| `generate-agent-card.py` | Docstring: `src/a2a/agent-card.json` → `ops/services/a2a/agent-card.json` | 5 |

## Shell Scripts Modified (23 total)

### `ops/scripts/` → `ops/scripts/`
| File | Specific old ref | Specific new ref |
|------|-----------------|------------------|
| `agent-ip-submission.sh` | `${CORTEX_REPO}/ops/scripts/manage/deploy-blocked-ips.sh` | `${CORTEX_REPO}/ops/scripts/manage/deploy-blocked-ips.sh` |
| `cron-auto-remediate.sh` | `CORTEX_SCRIPTS="${CORTEX_REPO}/src/scripts"` | `CORTEX_SCRIPTS="${CORTEX_REPO}/ops/scripts"` |
| `cron-auto-remediate.sh` | `git status --porcelain -- ops/scripts/` | `git status --porcelain -- ops/scripts/` |
| `send-agent-learning.sh` | `REPO_SCRIPTS="${HOME}/hermes-cortex/src/scripts"` | `REPO_SCRIPTS="${HOME}/hermes-cortex/ops/scripts"` |
| `setup-agent-inbox.sh` | `bash "${HOME}/hermes-cortex/ops/scripts/cortex-update.sh"` | `bash "${HOME}/hermes-cortex/ops/scripts/cortex-update.sh"` |
| `install-post-commit-hook.sh` | `NOTIFY_SCRIPT="${REPO_DIR}/ops/scripts/post-commit-notify.sh"` | `NOTIFY_SCRIPT="${REPO_DIR}/ops/scripts/post-commit-notify.sh"` |
| `pre-commit-doc-audit.sh` | `grep -c '^ops/scripts/'` | `grep -c '^ops/scripts/'` |
| `change-validate.sh` | `CORTEX_UPDATE="${REPO_ROOT}/ops/scripts/cortex-update.sh"` | `CORTEX_UPDATE="${REPO_ROOT}/ops/scripts/cortex-update.sh"` |
| `seed-project.sh` | `${REPO_DIR}/ops/scripts/install/merge-agents-md.py` | `${REPO_DIR}/ops/scripts/install/merge-agents-md.py` |
| `seed-project.sh` | `${REPO_DIR}/ops/scripts/pre-commit-score` | `${REPO_DIR}/ops/scripts/pre-commit-score` |
| `nginx-security-scanner.sh` | `${CORTEX_REPO}/ops/scripts/manage/deploy-blocked-ips.sh` | `${CORTEX_REPO}/ops/scripts/manage/deploy-blocked-ips.sh` |
| `cortex-profile.sh` | `Usage: bash ops/scripts/cortex-profile.sh` | `Usage: bash ops/scripts/cortex-profile.sh` |
| `cortex-update.sh` | `${REPO_DIR}/ops/scripts/install/os-config.sh` | `${REPO_DIR}/ops/scripts/install/os-config.sh` |

### `deploy/nginx/` → `ops/install/deploy/nginx/`
| File | Specific old ref | Specific new ref |
|------|-----------------|------------------|
| `agent-ip-submission.sh` | `${CORTEX_REPO}/deploy/nginx/blocked_ips.*` | `${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.*` |
| `agent-ip-submission.sh` | `git add deploy/nginx/blocked_ips.*` | `git add ops/install/deploy/nginx/blocked_ips.*` |
| `deploy-blocked-ips.sh` | `${CORTEX_REPO}/deploy/nginx/fix-blocked-ips.py` | `${CORTEX_REPO}/ops/install/deploy/nginx/fix-blocked-ips.py` |
| `nginx-threat-pipeline.sh` | `${CORTEX_REPO}/deploy/nginx/blocked_ips.*` (12 occurrences) | `${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.*` |
| `nginx-threat-pipeline.sh` | `mkdir -p "${CORTEX_REPO}/deploy/nginx"` | `mkdir -p "${CORTEX_REPO}/ops/install/deploy/nginx"` |
| `nginx-threat-pipeline.sh` | `git add/commit deploy/nginx/blocked_ips.add` | `git add/commit ops/install/deploy/nginx/blocked_ips.add` |
| `nginx-security-scanner.sh` | `BLOCKED_IPS="${CORTEX_REPO}/deploy/nginx/blocked_ips.add"` | `BLOCKED_IPS="${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.add"` |
| `install-nginx.sh` | `${SCRIPT_DIR}/../deploy/nginx/hermes-zone-defs.conf` | `${SCRIPT_DIR}/../ops/install/deploy/nginx/hermes-zone-defs.conf` |
| `install-nginx.sh` | `${SCRIPT_DIR}/../deploy/nginx/hermes-services.conf` | `${SCRIPT_DIR}/../ops/install/deploy/nginx/hermes-services.conf` |
| `cortex-update.sh` | `local nginx_src_dir="${REPO_DIR}/deploy/nginx"` | `local nginx_src_dir="${REPO_DIR}/ops/install/deploy/nginx"` |
| `cortex-update.sh` | `local src_dir="${REPO_DIR}/deploy/nginx"` | `local src_dir="${REPO_DIR}/ops/install/deploy/nginx"` |
| `change-validate.sh` | `deploy/nginx/hermes-services.conf` | `ops/install/deploy/nginx/hermes-services.conf` |
| `cortex-update.sh` | `register "deploy/docker-compose.langfuse.yml"` | `register "ops/install/deploy/docker-compose.langfuse.yml"` |
| `cortex-setup-langfuse.sh` | `${SCRIPT_DIR}/../../deploy/docker-compose.langfuse.yml` | `${SCRIPT_DIR}/../../ops/install/deploy/docker-compose.langfuse.yml` |
| `cortex-update.sh` | `deploy/hermes-services.env`, `deploy/nginx/hermes-services.env` | `ops/install/deploy/hermes-services.env`, `ops/install/deploy/nginx/hermes-services.env` |

### `skills/` → `runtime/skills/`
| File | Specific old ref | Specific new ref |
|------|-----------------|------------------|
| `collect-agent-skills.sh` | `REPO_SKILLS_DIR="$REPO_DIR/src/skills"` | `REPO_SKILLS_DIR="$REPO_DIR/runtime/skills"` |
| `pre-commit-doc-audit.sh` | `grep -c '^skills/'` | `grep -c '^runtime/skills/'` |
| `cortex-update.sh` | `local skill_repo="${REPO_DIR}/src/skills"` | `local skill_repo="${REPO_DIR}/runtime/skills"` |

### `src/offline/` → `ops/offline/`
| File | Specific old ref | Specific new ref |
|------|-----------------|------------------|
| `daily-lesson-mine.sh` | `"${CORTEX_REPO:-}/src/offline/session_mine.py"` | `"${CORTEX_REPO:-}/ops/offline/session_mine.py"` |
| `offline_code_index_cron.sh` | `~/hermes-cortex/ops/offline/offline_code.sh` | `~/hermes-cortex/ops/offline/offline_code.sh` |
| `cortex-update.sh` | `local corpus_src="${REPO_DIR}/src/offline/code-corpus"` | `local corpus_src="${REPO_DIR}/ops/offline/code-corpus"` |

### `src/mcp-servers/` → `ops/services/` (loop-gov-mcp.sh)
| Path component | Old | New |
|----------------|-----|-----|
| venv location | `~/.hermes-cortex/mcp-servers/venv` | `~/.hermes-cortex/services/venv` |
| script path | `$HOME/hermes-cortex/runtime/mcp-servers/loop-gov-mcp.py` | `$HOME/hermes-cortex/ops/services/loop-gov-mcp.py` |

### `core/governance/` → `core/governance/`
| File | Specific old ref | Specific new ref |
|------|-----------------|------------------|
| `setup.sh` | `"${HOME}/hermes-cortex/src/loop-governance"` | `"${HOME}/hermes-cortex/core/governance"` |
| `update.sh` | `"${HOME}/hermes-cortex/src/loop-governance"` (2 occurrences) | `"${HOME}/hermes-cortex/core/governance"` |
| `update.sh` | GitHub URL `main/core/governance/VERSION` | `main/core/governance/VERSION` |
| `update.sh` | tarball extract `hermes-cortex-main/core/governance/` | `hermes-cortex-main/core/governance/` |
| `cortex-update.sh` | `$HOME/src/hermes-cortex` (typo) | `$HOME/hermes-cortex` |

### Comment/Docs-only paths (in message bodies sent to agents)
| File | Old instruction | New instruction |
|------|----------------|----------------|
| `request-skill-reports.sh` | `bash ~/hermes-cortex/ops/scripts/manage/collect-agent-skills.sh` | ops equivalent instruction |

## Issues Encountered

### Escape-drift in heredoc grep patterns
The `patch` tool's fuzzy matching corrupted a `grep -oP` pattern inside a
bash `-c` string in `nginx-threat-pipeline.sh`. The pattern had complex
single-quote escaping (`'\\'"'"'[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+'\\'"'"'`)
inside a heredoc, and the patch tool converted `\\\\` to `\\\\` (double
to quadruple backslash) and stripped leading `\\'`.

**Lesson:** Always run `bash -n` on all changed `.sh` files after bulk
patches. The nginx-threat-pipeline.sh line 149 corruption would have
caused a runtime error.

### Indentation gap from partial patch
A second patch that overlapped with a previous one on the same line range
created an indentation mismatch:
```
-    echo "..." >> file
+    echo "..." >> file    # wrong: lost indentation level
```
The fix was a follow-up patch to restore 4-space indentation.

**Lesson:** When patching overlapping regions (same file, nearby lines),
re-read the file between patches to verify line alignment.

## Tool-Usage Insight

`search_files` (ripgrep backend) returned 0 results for the pattern `"src"`
because of quote escaping. Terminal `grep -rn '"src"'` found all matches.
**Always use terminal grep for pathlib literal searches.**

For continuous-string paths like `ops/scripts/` and `deploy/nginx/`,
`search_files` works fine. For pathlib-based refs (`"src" / "scripts"`),
use terminal grep.

## Verified

- All 24 `.sh` files pass `bash -n` syntax check.
- 4 Python files compiled cleanly with `py_compile.compile(path, doraise=True)`.
- Final sweep: zero stale `ops/scripts/`, `src/offline/`, `skills/`, `src/mcp-servers/`,
  `core/governance/`, `deploy/nginx/`, or `deploy/docker-compose.langfuse`
  references remain in `~/.hermes/scripts/`.
