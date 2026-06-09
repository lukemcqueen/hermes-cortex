#!/bin/bash
set -euo pipefail

process_repo() {
  local repo="$1"
  local push_branch="${2:-main}"
  local name
  name=$(basename "$repo")
  echo ""
  echo "============================================================"
  echo "  PROCESSING: $name"
  echo "  Path: $repo"
  echo "============================================================"

  cd "$repo"

  # Step 1: Delete agentkore/opencode artifacts from disk
  echo "[1] Removing .agentkore, .opencode, opencode.json..."
  rm -rf .agentkore .opencode opencode.json 2>/dev/null || true

  # Step 2: Update .gitignore
  echo "[2] Updating .gitignore..."
  if [ -f .gitignore ]; then
    # Add .agentkore/ if not present
    if ! grep -q '^\.agentkore' .gitignore 2>/dev/null; then
      echo '' >> .gitignore
      echo '.agentkore/' >> .gitignore
      echo "  -> Added .agentkore/ to .gitignore"
    else
      echo "  -> .agentkore/ already in .gitignore"
    fi
    # Add .opencode/ if not present
    if ! grep -q '^\.opencode' .gitignore 2>/dev/null; then
      echo '' >> .gitignore
      echo '.opencode/' >> .gitignore
      echo "  -> Added .opencode/ to .gitignore"
    else
      echo "  -> .opencode/ already in .gitignore"
    fi
  else
    echo '.agentkore/' > .gitignore
    echo '.opencode/' >> .gitignore
    echo "  -> Created .gitignore with .agentkore/ and .opencode/"
  fi

  # Step 3: Update AGENTS.md - replace agentkore/opencode refs with hermes
  echo "[3] Updating AGENTS.md..."
  if [ -f AGENTS.md ]; then
    # Check if this is the rails-fleet-operator-website variant (different template)
    if grep -q "AgentKore with OpenCode-native skills" AGENTS.md 2>/dev/null; then
      echo "  -> Using rails-fleet-operator variant updates"
      sed -i '' 's/AgentKore with OpenCode-native skills/Hermes Cortex with native skills/g' AGENTS.md
      sed -i '' 's/\.opencode\/skills\//\.hermes\/skills\//g' AGENTS.md
      sed -i '' 's/\.opencode\/skill\//\.hermes\/skill\//g' AGENTS.md
      sed -i '' 's/OpenCode\/proxy/Hermes\/proxy/g' AGENTS.md
      sed -i '' 's/AgentKore/Hermes Cortex/g' AGENTS.md
      sed -i '' 's/agentkore/hermes-cortex/g' AGENTS.md
      sed -i '' 's/opencode/hermes/g' AGENTS.md
    else
      echo "  -> Using standard template updates"
      sed -i '' 's/# AgentKore Instructions/# Hermes Cortex Instructions/g' AGENTS.md
      sed -i '' 's/AgentKore uses a two-tier architecture/Hermes Cortex uses a two-tier architecture/g' AGENTS.md
      sed -i '' 's/| Orchestrator | Hermes (OpenCode Zen) |/| Orchestrator | Hermes |/g' AGENTS.md
      sed -i '' 's/| Executor | OpenCode CLI |/| Executor | Hermes CLI |/g' AGENTS.md
      sed -i '' 's/\.agentkore\/sessions\/current\.md/memory\/session\.md/g' AGENTS.md
      sed -i '' 's/`agentkore-router`/`hermes-router`/g' AGENTS.md
      sed -i '' 's/`opencode-delegation`/`hermes-delegation`/g' AGENTS.md
      sed -i '' 's/\.agentkore\/hermes\/skills\//\.hermes\/skills\//g' AGENTS.md
      sed -i '' 's/\.opencode\/skills\//\.hermes\/skills\//g' AGENTS.md
      sed -i '' 's/\.opencode\/optional-skills\//\.hermes\/skills\//g' AGENTS.md
      sed -i '' 's/`opencode-instructions\.md`/hermes instructions/g' AGENTS.md
      sed -i '' 's/| Core | `\.opencode\/skills\/`/| Core | `\.hermes\/skills\/`/g' AGENTS.md
      sed -i '' 's/| Optional | `\.opencode\/optional-skills\/`/| Optional | `\.hermes\/skills\/`/g' AGENTS.md
      sed -i '' 's/Load opencode-delegation skill/Load hermes-delegation skill/g' AGENTS.md
      sed -i '' 's/| \*\*Session state\*\* | `\.agentkore\/sessions\/current\.md`/| **Session state** | `memory\/session\.md`/g' AGENTS.md
      sed -i '' 's/AgentKore manages state across four layers/Hermes Cortex manages state across four layers/g' AGENTS.md
      sed -i '' 's/AgentKore/Hermes Cortex/g' AGENTS.md
      sed -i '' 's/agentkore/hermes/g' AGENTS.md
    fi
    echo "  -> AGENTS.md updated"
  fi

  # Step 4: Check if git repo exists, then git add, commit, push
  if [ -d .git ]; then
    echo "[4] Git add and commit..."
    git add -A
    if ! git diff --cached --quiet; then
      git commit -m 'chore: migrate from agentkore/opencode to hermes-cortex'
      echo "  -> Committed"
    else
      echo "  -> No changes to commit (skipping)"
    fi

    # Step 5: Push (if remote exists)
    echo "[5] Attempting git push..."
    # Check if remote 'origin' exists
    if git remote get-url origin &>/dev/null; then
      if git push origin "$push_branch" 2>/dev/null; then
        echo "  -> Push successful"
      else
        echo "  -> Push failed, trying pull --rebase first"
        git pull --rebase origin "$push_branch" 2>/dev/null || true
        git push origin "$push_branch"
        echo "  -> Push successful after rebase"
      fi
    else
      echo "  -> No 'origin' remote found, skipping push"
    fi
  else
    echo "[4] Not a git repository — skipping git operations"
  fi

  echo "  DONE: $name"
}

# --- Process all repos ---

# Git repos with main branch + remote
process_repo "/Users/luke/Developer/PERSONAL/ebm/ebm-website" "main"
process_repo "/Users/luke/Developer/PERSONAL/fleet-operator/rails-fleet-operator-website" "main"
process_repo "/Users/luke/Developer/ACME/acme-av" "main"
process_repo "/Users/luke/Developer/ACME/acme-license" "main"

# acme-live: git repo but NO remote
process_repo "/Users/luke/Developer/ACME/acme-live" "main"

# acme-matching
process_repo "/Users/luke/Developer/ACME/acme-matching" "main"

# acme-mwi: on feature/new-feature branch
process_repo "/Users/luke/Developer/ACME/acme-mwi" "feature/new-feature"

# Non-git repos: clean up files only
echo ""
echo "============================================================"
echo "  NON-GIT REPOS (file cleanup only)"
echo "============================================================"

for repo in \
  /Users/luke/Developer/AI/brain \
  /Users/luke/Developer/AI/llama-cpp-launcher \
  /Users/luke/Developer/PERSONAL/fleet-operator/nextjs-fleet-operator-website \
  /Users/luke/Developer/PERSONAL/example/example-app; do
  name=$(basename "$repo")
  echo ""
  echo "--- $name ---"
  cd "$repo"

  echo "[1] Removing .agentkore, .opencode, opencode.json..."
  rm -rf .agentkore .opencode opencode.json 2>/dev/null || true

  echo "[2] Updating .gitignore..."
  if [ -f .gitignore ]; then
    if ! grep -q '^\.agentkore' .gitignore 2>/dev/null; then
      echo '' >> .gitignore
      echo '.agentkore/' >> .gitignore
      echo "  -> Added .agentkore/"
    fi
    if ! grep -q '^\.opencode' .gitignore 2>/dev/null; then
      echo '' >> .gitignore
      echo '.opencode/' >> .gitignore
      echo "  -> Added .opencode/"
    fi
  else
    echo '.agentkore/' > .gitignore
    echo '.opencode/' >> .gitignore
    echo "  -> Created .gitignore"
  fi

  echo "[3] Updating AGENTS.md..."
  if [ -f AGENTS.md ]; then
    sed -i '' 's/agentkore/hermes/gI' AGENTS.md 2>/dev/null || true
    sed -i '' 's/opencode/hermes/gI' AGENTS.md 2>/dev/null || true
    sed -i '' 's/AgentKore/Hermes Cortex/g' AGENTS.md 2>/dev/null || true
    echo "  -> AGENTS.md updated"
  fi

  echo "  DONE: $name (non-git)"
done

echo ""
echo "============================================================"
echo "  ALL REPOS PROCESSED"
echo "============================================================"
