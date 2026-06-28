#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  seed-project.sh — Deploy Hermes Cortex harness to a project
#
#  One-command bootstrap: AGENTS.md, .hermes-cortex/ infra,
#  loop-governance scoring, pre-commit hooks, project skills.
#
#  Usage:
#    seed-project.sh --project=<path>                         # default: merge mode, all components
#    seed-project.sh --project=<path> --mode=overwrite        # destructive (backup still created)
#    seed-project.sh --project=<path> --mode=diff             # preview only, no writes
#    seed-project.sh --project=<path> --components=AGENTS.md,.hermes-cortex
#    seed-project.sh --project=<path> --name="My API"         # custom project name
#    seed-project.sh --project=<path> --template=./custom.md  # custom AGENTS.md template
#    seed-project.sh --project=<path> --skill-refs=score-cycle,change-test-loop
#    seed-project.sh --restore=<path>                         # restore from last backup
#    seed-project.sh --restore=<path>@<timestamp>             # restore specific backup
#    seed-project.sh --list-backups=<path>                    # show available backups
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
error() { printf "${RED}✗${RESET} %s\n" "$*" >&2; }
die()   { error "$*"; exit 1; }
header(){ printf "\n${BOLD}%s${RESET}\n" "$*"; }

# ── Paths ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"  # hermes-cortex repo root
TEMPLATES_DIR="${REPO_DIR}/docs/templates"
AGENTS_TEMPLATE="${TEMPLATES_DIR}/AGENTS.seed.md"
CORTEX_COMMIT="$(cd "$REPO_DIR" && git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
HERMES_CORTEX_SKILLS="${HOME}/.hermes/skills"  # resolved via symlink

# ── Help ─────────────────────────────────────────────────────
show_help() {
  cat <<EOF
seed-project.sh — Deploy Hermes Cortex harness to a project

USAGE:
  seed-project.sh --project=<path> [options]

REQUIRED:
  --project=<path>     Target project directory

OPTIONS:
  --mode=merge         (default) Backup existing, only write changed files
  --mode=overwrite     Backup existing, overwrite everything
  --mode=diff          Show what would change, no writes
  --components=ALL     (default) Deploy everything
  --components=list    Comma-separated: AGENTS.md,.hermes-cortex,pre-commit,loop-gov,skills
  --name=<name>        Project display name (for AGENTS.md placeholder)
  --template=<path>    Custom AGENTS.md template file
  --skill-refs=list    Comma-separated skill names to deploy as project overrides
  --no-backup          Skip backup (risky — use with --mode=overwrite only)

RESTORE:
  --restore=<path>              Restore project from most recent backup
  --restore=<path>@<timestamp>  Restore specific backup
  --list-backups=<path>         List available backups for a project

EXAMPLES:
  seed-project.sh --project=~/Developer/my-api --mode=diff
  seed-project.sh --project=~/Developer/my-api --name="Payment API" --skill-refs=change-test-loop
  seed-project.sh --project=~/Developer/my-api --components=AGENTS.md,.hermes-cortex
  seed-project.sh --list-backups=~/Developer/my-api
  seed-project.sh --restore=~/Developer/my-api
  seed-project.sh --restore=~/Developer/my-api@20260626_150000
EOF
  exit 0
}

# ── Parse arguments ──────────────────────────────────────────
PROJECT=""
MODE="merge"
COMPONENTS="ALL"
PROJECT_NAME=""
CUSTOM_TEMPLATE=""
SKILL_REFS=""
NO_BACKUP=false

for arg in "$@"; do
  case "$arg" in
    --help|-h)        show_help ;;
    --project=*)      PROJECT="${arg#*=}" ;;
    --mode=*)         MODE="${arg#*=}" ;;
    --components=*)   COMPONENTS="${arg#*=}" ;;
    --name=*)         PROJECT_NAME="${arg#*=}" ;;
    --template=*)     CUSTOM_TEMPLATE="${arg#*=}" ;;
    --skill-refs=*)   SKILL_REFS="${arg#*=}" ;;
    --no-backup)      NO_BACKUP=true ;;
    --restore=*)      RESTORE_TARGET="${arg#*=}" ;;
    --list-backups=*) LIST_BACKUPS="${arg#*=}" ;;
    *)                die "Unknown argument: $arg (use --help)" ;;
  esac
done

# ── Validate mode ────────────────────────────────────────────
case "$MODE" in
  merge|overwrite|diff) ;;
  *) die "Invalid mode: $MODE (use merge, overwrite, or diff)" ;;
esac

# ── Delta engine (same as cortex-update.sh) ──────────────────
needs_update() {
  local src="$1" dest="$2"
  [[ ! -f "$dest" ]] && return 0
  [[ ! -f "$src" ]] && return 1
  local src_hash dest_hash
  if command -v sha256sum &>/dev/null; then
    src_hash=$(sha256sum "$src" 2>/dev/null | cut -d' ' -f1)
    dest_hash=$(sha256sum "$dest" 2>/dev/null | cut -d' ' -f1)
  elif command -v shasum &>/dev/null; then
    src_hash=$(shasum -a 256 "$src" 2>/dev/null | cut -d' ' -f1)
    dest_hash=$(shasum -a 256 "$dest" 2>/dev/null | cut -d' ' -f1)
  else
    [[ "$src" -nt "$dest" ]] && return 0
    return 1
  fi
  [[ "$src_hash" != "$dest_hash" ]] && return 0
  return 1
}

# ── Backup ───────────────────────────────────────────────────
BACKUP_DIR=""
BACKUP_MANIFEST=""

create_backup() {
  local project="$1" ts
  ts="$(date -u +'%Y%m%d_%H%M%S')-$RANDOM"
  BACKUP_DIR=""
  BACKUP_MANIFEST=""

  # Skip backup entirely if nothing exists to save (no .hermes-cortex, no AGENTS.md, no pre-commit)
  # Avoids creating empty .hermes-cortex/ as side effect (bug: --components=AGENTS.md)
  local has_anything=false
  [[ -f "${project}/AGENTS.md" ]] && has_anything=true
  [[ -d "${project}/.hermes-cortex" ]] && has_anything=true
  [[ -f "${project}/.git/hooks/pre-commit" ]] && has_anything=true
  $has_anything || return 0

  BACKUP_DIR="${project}/.hermes-cortex/.seed-backups/${ts}"
  BACKUP_MANIFEST="${BACKUP_DIR}/manifest.json"
  mkdir -p "$BACKUP_DIR"
  header "Backing up existing files → ${BACKUP_DIR/$HOME/~}"

  # Backup AGENTS.md
  if [[ -f "${project}/AGENTS.md" ]]; then
    cp "${project}/AGENTS.md" "${BACKUP_DIR}/AGENTS.md"
    info "  AGENTS.md"
  fi

  # Backup .hermes-cortex/ structure (exclude .seed-backups to avoid circular copy)
  if [[ -d "${project}/.hermes-cortex" ]]; then
    mkdir -p "${BACKUP_DIR}/.hermes-cortex"
    # Copy everything except .seed-backups (which contains the backup we're writing)
    for item in "${project}/.hermes-cortex/"* "${project}/.hermes-cortex"/.[!.]*; do
      local base="$(basename "$item")"
      [[ "$base" == ".seed-backups" ]] && continue
      [[ "$base" == "." || "$base" == ".." ]] && continue
      cp -r "$item" "${BACKUP_DIR}/.hermes-cortex/" 2>/dev/null || true
    done
    info "  .hermes-cortex/"
  fi

  # Backup pre-commit hook
  if [[ -f "${project}/.git/hooks/pre-commit" ]]; then
    mkdir -p "${BACKUP_DIR}/.git/hooks"
    cp "${project}/.git/hooks/pre-commit" "${BACKUP_DIR}/.git/hooks/pre-commit"
    info "  .git/hooks/pre-commit"
  fi

  # Write manifest
  cat > "$BACKUP_MANIFEST" <<JSON
{
  "timestamp": "${ts}",
  "project": "${project}",
  "cortex_commit": "${CORTEX_COMMIT}",
  "files": [
    $(for f in "$BACKUP_DIR"/*; do
        [[ -f "$f" ]] && echo "\"$(basename "$f")\","
      done | sed '$s/,$//')
  ],
  "mode": "${MODE}"
}
JSON
  info "  manifest.json written"
}

list_backups() {
  local project="$1"
  local backup_root="${project}/.hermes-cortex/.seed-backups"
  if [[ ! -d "$backup_root" ]]; then
    echo "No backups found for ${project}."
    return 0
  fi
  echo "Available backups for ${project/$HOME/~}"
  local count=0
  for dir in "$backup_root"/*/; do
    [[ -d "$dir" ]] || continue
    local ts
    ts="$(basename "$dir")" || true
    local manifest="${dir}/manifest.json"
    if [[ -f "$manifest" ]]; then
      local mode="?"
      mode=$(python3 -c "import json; print(json.load(open('${manifest}')).get('mode','?'))" 2>/dev/null) || mode="?"
      local cortex_commit="?"
      cortex_commit=$(python3 -c "import json; print(json.load(open('${manifest}')).get('cortex_commit','?'))" 2>/dev/null) || cortex_commit="?"
      local file_count
      file_count=$(ls -1 "$dir" | grep -v manifest.json | wc -l | tr -d ' ') || true
      echo "  ${ts}  ${file_count} files  mode=${mode}  cortex=${cortex_commit}"
    else
      echo "  ${ts}  (no manifest)"
    fi
    count=$((count + 1))
  done
  if [[ "$count" -eq 0 ]]; then
    echo "  (no backups found)"
  fi
}

restore_backup() {
  local target="$1"
  local project ts
  if [[ "$target" == *@* ]]; then
    project="${target%%@*}"
    ts="${target#*@}"
  else
    project="$target"
    ts=""
  fi

  project="$(cd "$project" 2>/dev/null && pwd)" || die "Project not found: $(basename "$target" 2>/dev/null || echo "$target")"
  local backup_root="${project}/.hermes-cortex/.seed-backups"

  # Find the backup to restore
  local restore_dir=""
  if [[ -n "$ts" ]]; then
    restore_dir="${backup_root}/${ts}"
    [[ -d "$restore_dir" ]] || die "Backup not found: ${ts} (use --list-backups=${project})"
  else
    restore_dir=$(ls -dt "${backup_root}"/*/ 2>/dev/null | head -1 | tr -d '\n')
    [[ -n "$restore_dir" ]] || die "No backups found for ${project}."
  fi

  local ts_label="$(basename "$restore_dir")"
  header "Restoring from backup: ${ts_label}"

  local errors=0
  local has_restore=false

  # Restore AGENTS.md
  if [[ -f "${restore_dir}/AGENTS.md" ]]; then
    cp "${restore_dir}/AGENTS.md" "${project}/AGENTS.md"
    info "  Restored AGENTS.md"
    has_restore=true
  fi

  # Restore .hermes-cortex/ — only if backup actually has it
  if [[ -d "${restore_dir}/.hermes-cortex" ]]; then
    # Stage backup content to /tmp/ BEFORE moving .hermes-cortex
    # (backup lives inside .hermes-cortex/.seed-backups — would become unreachable)
    local stage_dir
    stage_dir="$(mktemp -d "/tmp/.seed-restore-stage-XXXXXX")"
    cp -r "${restore_dir}/.hermes-cortex/"* "$stage_dir/" 2>/dev/null || true

    # Move current .hermes-cortex to temp sibling in case restore goes wrong
    local tmp_backup="${project}/.hermes-cortex.tmp-restore"
    if [[ -d "${project}/.hermes-cortex" ]]; then
      mv "${project}/.hermes-cortex" "${tmp_backup}"
    fi

    # Restore from staged copy
    cp -r "$stage_dir/" "${project}/.hermes-cortex/" && {
      # Re-insert backups from moved-away .hermes-cortex
      if [[ -d "${tmp_backup}" ]]; then
        if [[ -d "${tmp_backup}/.seed-backups" ]]; then
          mkdir -p "${project}/.hermes-cortex/.seed-backups"
          cp -r "${tmp_backup}/.seed-backups/"* "${project}/.hermes-cortex/.seed-backups/" 2>/dev/null || true
        fi
        rm -rf "${tmp_backup}"
      fi
      rm -rf "$stage_dir"
      info "  Restored .hermes-cortex/"
      has_restore=true
    } || {
      # cp failed — move the original back
      warn "  Failed to restore .hermes-cortex/ from backup"
      rm -rf "$stage_dir"
      if [[ -d "${tmp_backup}" ]]; then
        mv "${tmp_backup}" "${project}/.hermes-cortex"
      fi
    }
  fi

  # Restore pre-commit hook
  if [[ -f "${restore_dir}/.git/hooks/pre-commit" ]]; then
    mkdir -p "${project}/.git/hooks"
    cp "${restore_dir}/.git/hooks/pre-commit" "${project}/.git/hooks/pre-commit"
    chmod +x "${project}/.git/hooks/pre-commit"
    info "  Restored .git/hooks/pre-commit"
    has_restore=true
  fi

  if [[ "$has_restore" == "false" ]]; then
    warn "Backup had no files to restore (first seed has nothing to back up)"
  elif [[ "$errors" -gt 0 ]]; then
    warn "${errors} file(s) could not be restored"
  else
    info "Restore complete — ${ts_label}"
  fi
}

# ── Component deployment ─────────────────────────────────────

deploy_agents_md() {
  local project="$1" template="$2" name="$3"
  local dest="${project}/AGENTS.md"
  local src="${template:-$AGENTS_TEMPLATE}"

  [[ "${COMPONENTS}" != "ALL" && "${COMPONENTS}" != *"AGENTS.md"* ]] && return 0
  [[ -f "$src" ]] || { warn "AGENTS.md template not found: $src"; return 0; }

  # Read template, substitute placeholders
  local content
  content=$(<"$src")
  content="${content//"{{PROJECT_NAME}}"/${name:-$(basename "$project")}}"
  content="${content//"{{PROJECT_DESCRIPTION}}"/$(basename "$project") — seeded project}"
  content="${content//"{{SEED_DATE}}"/$(date -u +'%Y-%m-%d')}"
  content="${content//"{{SEED_COMMIT}}"/${CORTEX_COMMIT}}"

  if [[ "$MODE" == "diff" ]]; then
    if [[ ! -f "$dest" ]] || [[ "$(cat "$dest" 2>/dev/null)" != "$content" ]]; then
      echo "  would update: AGENTS.md"
    fi
    return 0
  fi

  if [[ "$MODE" == "overwrite" ]] || [[ ! -f "$dest" ]] || [[ "$(cat "$dest" 2>/dev/null)" != "$content" ]]; then
    echo "$content" > "$dest"
    info "  AGENTS.md → ${dest/$HOME/~}"
  else
    info "  AGENTS.md — unchanged"
  fi
}

deploy_cortex_dir() {
  local project="$1"
  [[ "${COMPONENTS}" != "ALL" && "${COMPONENTS}" != *".hermes-cortex"* ]] && return 0

  local dirs=(
    "${project}/.hermes-cortex/sessions/archive"
    "${project}/.hermes-cortex/memory"
    "${project}/.hermes-cortex/skills"
  )

  if [[ "$MODE" == "diff" ]]; then
    local missing=0
    for d in "${dirs[@]}"; do
      [[ -d "$d" ]] || { echo "  would create: ${d/$HOME/~}"; missing=$((missing + 1)); }
    done
    [[ "$missing" -eq 0 ]] && echo "  .hermes-cortex/ — exists"
    return 0
  fi

  local created=0
  for d in "${dirs[@]}"; do
    if [[ ! -d "$d" ]]; then
      mkdir -p "$d"
      created=$((created + 1))
    fi
  done

  # .gitkeep files
  touch "${project}/.hermes-cortex/.gitkeep"
  touch "${project}/.hermes-cortex/sessions/.gitkeep"
  touch "${project}/.hermes-cortex/memory/.gitkeep"
  touch "${project}/.hermes-cortex/skills/.gitkeep"

  # .gitignore for memory/ (never commit agent memory)
  local gitignore="${project}/.hermes-cortex/.gitignore"
  if [[ ! -f "$gitignore" ]]; then
    cat > "$gitignore" <<'EOF'
# Hermes Cortex — never commit agent memory
memory/
*.db
*.sqlite
.env
*.pem
*.key
EOF
  fi

  if [[ "$created" -gt 0 ]]; then
    info "  .hermes-cortex/ — ${created} dir(s) created"
  else
    info "  .hermes-cortex/ — exists"
  fi
}

deploy_precommit() {
  local project="$1"
  [[ "${COMPONENTS}" != "ALL" && "${COMPONENTS}" != *"pre-commit"* ]] && return 0

  local hook_script="${SCRIPT_DIR}/pre-commit-score"
  local hook_dest="${project}/.git/hooks/pre-commit"

  if [[ ! -d "${project}/.git" ]]; then
    warn "  Not a git repo — skipping pre-commit hook"
    return 0
  fi

  if [[ ! -f "$hook_script" ]]; then
    warn "  pre-commit-score not found at ${hook_script} — skipping hook install"
    return 0
  fi

  if [[ "$MODE" == "diff" ]]; then
    if needs_update "$hook_script" "$hook_dest"; then
      echo "  would install: .git/hooks/pre-commit"
    else
      echo "  .git/hooks/pre-commit — up to date"
    fi
    return 0
  fi

  # Use install-score-hook.sh if available (preferred)
  local install_hook="${SCRIPT_DIR}/install-score-hook.sh"
  if [[ -f "$install_hook" ]]; then
    bash "$install_hook" --path "$project" 2>/dev/null && {
      info "  pre-commit hook installed (via install-score-hook.sh)"
      return 0
    }
  fi

  # Fallback: direct copy
  mkdir -p "${project}/.git/hooks"
  cp "$hook_script" "$hook_dest"
  chmod +x "$hook_dest"
  info "  pre-commit hook installed (direct)"
}

deploy_loop_gov() {
  local project="$1"
  [[ "${COMPONENTS}" != "ALL" && "${COMPONENTS}" != *"loop-gov"* ]] && return 0

  local lg_dir="${project}/.hermes-cortex/loop-governance"
  local lg_source="${REPO_DIR}/src/loop-governance"

  if [[ "$MODE" == "diff" ]]; then
    echo "  would create: ${lg_dir/$HOME/~}/score-cycle wrapper"
    echo "  would create: ${lg_dir/$HOME/~}/loop-feedback wrapper"
    return 0
  fi

  mkdir -p "$lg_dir"

  # Create score-cycle wrapper
  local score_wrapper="${lg_dir}/score-cycle"
  cat > "$score_wrapper" <<'BASH'
#!/usr/bin/env bash
# Wrapper: project-level score-cycle → global score-cycle
set -euo pipefail
exec score-cycle "$@"
BASH
  chmod +x "$score_wrapper"

  # Create loop-feedback wrapper
  local feedback_wrapper="${lg_dir}/loop-feedback"
  cat > "$feedback_wrapper" <<'BASH'
#!/usr/bin/env bash
# Wrapper: project-level loop-feedback → global loop-feedback
set -euo pipefail
exec loop-feedback "$@"
BASH
  chmod +x "$feedback_wrapper"

  # Add to .gitignore
  local gitignore="${project}/.hermes-cortex/.gitignore"
  if ! grep -q "loop-gov.db\|loop-governance" "$gitignore" 2>/dev/null; then
    cat >> "$gitignore" <<'EOF'

# Loop governance database
*.db
loop-gov.db
EOF
  fi

  info "  loop-gov wrappers in .hermes-cortex/loop-governance/"
}

deploy_skills() {
  local project="$1" refs="$2"
  [[ "${COMPONENTS}" != "ALL" && "${COMPONENTS}" != *"skills"* ]] && return 0
  [[ -z "$refs" && "${COMPONENTS}" != "ALL" ]] && return 0

  local project_skills="${project}/.hermes-cortex/skills"

  if [[ "$refs" == "ALL" || "$COMPONENTS" == "ALL" ]]; then
    # Default skill set for a seeded project
    refs="change-test-loop,engineering-approach,test-driven-development,save-lesson,spike,writing-plans"
  fi

  if [[ "$MODE" == "diff" ]]; then
    IFS=',' read -ra skills <<< "$refs"
    for skill in "${skills[@]}"; do
      local skill_trimmed="$(echo "$skill" | tr -d ' ')"
      # Search for the skill in ~/.hermes/skills/
      local skill_path
      skill_path=$(find -L "$HERMES_CORTEX_SKILLS" -maxdepth 3 -type d -name "$skill_trimmed" 2>/dev/null | head -1)
      local dest="${project_skills}/${skill_trimmed}/SKILL.md"
      if [[ -n "$skill_path" ]]; then
        if [[ -f "$dest" ]]; then
          echo "  skill ${skill_trimmed} — exists"
        else
          echo "  would link: ${skill_trimmed} → ${dest/$HOME/~}"
        fi
      else
        echo "  skill ${skill_trimmed} — NOT FOUND in global skills"
      fi
    done
    return 0
  fi

  IFS=',' read -ra skills <<< "$refs"
  local linked=0 not_found=0
  for skill in "${skills[@]}"; do
    local skill_trimmed="$(echo "$skill" | tr -d ' ')"
    [[ -z "$skill_trimmed" ]] && continue
    local skill_path
    skill_path=$(find -L "$HERMES_CORTEX_SKILLS" -maxdepth 3 -type d -name "$skill_trimmed" 2>/dev/null | head -1)
    local dest="${project_skills}/${skill_trimmed}"
    if [[ -n "$skill_path" ]] && [[ -f "${skill_path}/SKILL.md" ]]; then
      if [[ ! -d "$dest" ]]; then
        mkdir -p "$(dirname "$dest")"
        if [[ "$MODE" == "overwrite" ]]; then
          cp -r "$skill_path" "$dest"
        else
          cp -r "$skill_path" "$dest"
        fi
        linked=$((linked + 1))
      fi
    else
      not_found=$((not_found + 1))
    fi
  done

  if [[ "$linked" -gt 0 ]]; then
    info "  skills: ${linked} linked"
  fi
  if [[ "$not_found" -gt 0 ]]; then
    warn "  skills: ${not_found} not found in global skills"
  fi
}

# ── Summary report ───────────────────────────────────────────
print_summary() {
  local project="$1" mode="$2"
  local backup_ref="${BACKUP_DIR/$HOME/~}"
  header "━━━ Seed Summary ━━━"
  echo "  Project:  ${project/$HOME/~}"
  echo "  Mode:     ${mode}"
  [[ -n "$BACKUP_DIR" ]] && echo "  Backup:   ${backup_ref}"
  echo ""
  echo "  AGENTS.md, .hermes-cortex/, pre-commit, loop-gov, skills"
  echo "  To restore: seed-project.sh --restore=${project/$HOME/~}"
  echo "━━━━━━━━━━━━━━━━━━━━━"
}

# ── Main ─────────────────────────────────────────────────────

main() {
  # Handle restore/list-backups modes first
  if [[ -n "${LIST_BACKUPS:-}" ]]; then
    local project
    project="$(cd "$LIST_BACKUPS" 2>/dev/null && pwd)" || die "Project not found: $LIST_BACKUPS (use --list-backups=<path>)"
    list_backups "$project"
    return 0
  fi

  if [[ -n "${RESTORE_TARGET:-}" ]]; then
    restore_backup "$RESTORE_TARGET"
    return 0
  fi

  # Validate project
  [[ -z "$PROJECT" ]] && die "Required: --project=<path>"
  local resolved
  resolved="$(cd "$PROJECT" 2>/dev/null && pwd)" || die "Project not found: $PROJECT"
  PROJECT="$resolved"
  [[ -d "$PROJECT" ]] || die "Not a directory: $PROJECT"

  header "Seed Project: ${PROJECT/$HOME/~}"

  # Validate template
  local template="${CUSTOM_TEMPLATE:-$AGENTS_TEMPLATE}"
  [[ -f "$template" ]] || warn "AGENTS.md template not found: $template"

  # Diff mode: no backup, no changes
  if [[ "$MODE" == "diff" ]]; then
    header "Diff mode — showing what would change"
  else
    # Create backup (unless --no-backup)
    if [[ "$NO_BACKUP" == "true" ]]; then
      warn "Skipping backup (--no-backup set)"
    else
      create_backup "$PROJECT"
    fi
  fi

  # Deploy components
  deploy_agents_md "$PROJECT" "$template" "$PROJECT_NAME"
  deploy_cortex_dir "$PROJECT"
  deploy_precommit "$PROJECT"
  deploy_loop_gov "$PROJECT"
  deploy_skills "$PROJECT" "$SKILL_REFS"

  if [[ "$MODE" != "diff" ]]; then
    print_summary "$PROJECT" "$MODE"
  fi
}

main "$@"
