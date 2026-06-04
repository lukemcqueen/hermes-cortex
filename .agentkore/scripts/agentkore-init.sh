#!/usr/bin/env bash

set -euo pipefail
IFS=$'\n\t'

FORCE=false
ALL_SKILLS=false

usage() {
  echo "Usage: $0 [--force] [--all-skills]"
  echo ""
  echo "Options:"
  echo "  --force       Overwrite existing files without prompting"
  echo "  --all-skills  Ship all optional skills (default: 16 core skills only)"
}

# Parse args
for arg in "$@"; do
  case "$arg" in
    --force)
      FORCE=true
      ;;
    --all-skills)
      ALL_SKILLS=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      usage
      exit 1
      ;;
  esac
done

ROOT_DIR="$(pwd)"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[INFO] Installing AgentKore into root directory: $ROOT_DIR. Source directory is: $SRC_DIR"

copy_file() {
  local src="$1"
  local dest="$2"

  if [ -e "$dest" ] && [ "$FORCE" = false ]; then
    echo "[SKIP] $dest exists (use --force to overwrite)"
    return
  fi

  mkdir -p "$(dirname "$dest")"
  cp -f "$src" "$dest"
  echo "[COPY] $dest"
}

copy_dir() {
  local src="$1"
  local dest="$2"

  if [ -d "$dest" ] && [ "$FORCE" = false ]; then
    echo "[SKIP] $dest exists (use --force to overwrite)"
    return
  fi

  mkdir -p "$(dirname "$dest")"
  rm -rf "$dest"
  cp -r "$src" "$dest"
  echo "[COPY] $dest"
}

# Core files
copy_file "$SRC_DIR/AGENTS.md" "$ROOT_DIR/AGENTS.md"
copy_file "$SRC_DIR/opencode-instructions.md" "$ROOT_DIR/opencode-instructions.md"

# AgentKore system
copy_dir "$SRC_DIR/.agentkore" "$ROOT_DIR/.agentkore"


# Project docs and memory seeds
copy_file "$SRC_DIR/.agentkore/install_templates/docs/design/DESIGN.md" "$ROOT_DIR/docs/design/DESIGN.md"
copy_file "$SRC_DIR/.agentkore/install_templates/docs/DOCS-INDEX.md" "$ROOT_DIR/docs/DOCS-INDEX.md"
copy_dir "$SRC_DIR/.agentkore/install_templates/memory" "$ROOT_DIR/memory"

# OpenCode config template
copy_file "$SRC_DIR/.agentkore/install_templates/template_opencode.json" "$ROOT_DIR/opencode.json"

# Skills (optional: only if you distribute separately)
if [ -d "$SRC_DIR/.opencode" ]; then
  if [ "$ALL_SKILLS" = true ]; then
    # Install optional skills alongside core
    copy_dir "$SRC_DIR/.opencode" "$ROOT_DIR/.opencode"
    # Strip node_modules — shipped separately via npm install
    rm -rf "$ROOT_DIR/.opencode/node_modules"
    if [ -d "$SRC_DIR/.opencode/optional-skills" ]; then
      echo "[INFO] Installing all optional skills..."
      for s in "$SRC_DIR/.opencode/optional-skills"/*/; do
        name=$(basename "$s")
        dest="$ROOT_DIR/.opencode/skills/$name"
        if [ -d "$dest" ] && [ "$FORCE" = false ]; then
          echo "[SKIP] Skill '$name' already installed (use --force to overwrite)"
        else
          rm -rf "$dest"
          cp -r "$s" "$dest"
          echo "[COPY] .opencode/skills/$name"
        fi
      done
    fi
  else
    # Core skills only — always overwrite (removes deleted skills from target)
    # Use rsync --delete so self-deploy (SRC==ROOT) doesn't nuke source before copy
    mkdir -p "$ROOT_DIR/.opencode"
    rsync -a --delete "$SRC_DIR/.opencode/skills/" "$ROOT_DIR/.opencode/skills/" && \
      echo "[SYNC] .opencode/skills (forced — removes deleted skills from target)"
    # Also copy the optional-skills catalog (so ./run skills-install works later)
    if [ -d "$SRC_DIR/.opencode/optional-skills" ]; then
      copy_dir "$SRC_DIR/.opencode/optional-skills" "$ROOT_DIR/.opencode/optional-skills"
    fi
  fi
fi

# Install npm deps for OpenCode plugin if needed
if [ -f "$ROOT_DIR/.opencode/package.json" ] && [ ! -d "$ROOT_DIR/.opencode/node_modules" ]; then
  echo "[INFO] Installing OpenCode plugin dependencies..."
  (cd "$ROOT_DIR/.opencode" && npm install --no-audit --no-fund 2>/dev/null) || \
    echo "[WARN] npm install failed — install deps manually: cd .opencode && npm install"
fi

echo ""
echo "[SUCCESS] AgentKore installed"

if [ "$FORCE" = true ]; then
  echo "[WARNING] Files were overwritten due to --force"
fi