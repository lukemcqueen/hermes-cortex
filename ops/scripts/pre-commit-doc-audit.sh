#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# pre-commit-doc-audit.sh — Check that doc changes are reflected in DOCS-INDEX.md
#
# Runs as a pre-commit hook add-on. Checks if staged changes to
# docs/, ops/scripts/, runtime/skills/, ops/install/deploy/nginx/ are accompanied
# by corresponding updates to DOCS-INDEX.md, SKILLS-MANIFEST.md,
# or cortex-update.sh MAP.
#
# SILENT ON SUCCESS — only speaks when it finds problems.
# No_agent watchdog pattern: stay quiet when clean.
#
# Install:
#   ln -sf ~/hermes-cortex/ops/scripts/pre-commit-doc-audit.sh \
#     ~/hermes-cortex/.git/hooks/pre-commit-doc-audit
#   echo 'bash .git/hooks/pre-commit-doc-audit' >> ~/hermes-cortex/.git/hooks/pre-commit
#
# Or call manually before git commit:
#   bash ~/hermes-cortex/ops/scripts/pre-commit-doc-audit.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# Only check staged files
STAGED=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)

# Exit silently if nothing staged
[[ -z "$STAGED" ]] && exit 0

issues=0

# ── Check 1: New/changed .md files in docs/ should update DOCS-INDEX.md ──
DOCS_CHANGED=$(echo "$STAGED" | grep -c '^docs/.*\.md$' 2>/dev/null || true)
DOCS_INDEX_CHANGED=$(echo "$STAGED" | grep -c '^docs/DOCS-INDEX\.md$' 2>/dev/null || true)

if [[ "$DOCS_CHANGED" -gt 0 && "$DOCS_INDEX_CHANGED" -eq 0 ]]; then
    # Get the list of docs files that changed but are NOT DOCS-INDEX.md itself
    MISSING_DOCS=$(echo "$STAGED" | grep '^docs/.*\.md$' | grep -v '^docs/DOCS-INDEX\.md$' || true)
    for doc in $MISSING_DOCS; do
        # Skip docs that don't need indexing (internal references, CODE_OF_CONDUCT, etc.)
        case "$doc" in
            docs/CODE_OF_CONDUCT.md|docs/CONTRIBUTING.md|docs/SECURITY.md|docs/THIRD_PARTY_LICENSES.md|docs/design/*|docs/templates/*.plist)
                continue
                ;;
        esac
        echo "⚠️  DOCS AUDIT: $doc changed but docs/DOCS-INDEX.md was not updated."
        echo "   → Add/modify the entry for this file in docs/DOCS-INDEX.md"
        issues=$((issues + 1))
    done
fi

# ── Check 2: New/changed skills should update SKILLS-MANIFEST.md ──
SKILLS_CHANGED=$(echo "$STAGED" | grep -c '^.hermes-cortex/skills/' 2>/dev/null || true)
MANIFEST_CHANGED=$(echo "$STAGED" | grep -c '^docs/SKILLS-MANIFEST\.md$' 2>/dev/null || true)

if [[ "$SKILLS_CHANGED" -gt 0 && "$MANIFEST_CHANGED" -eq 0 ]]; then
    echo "⚠️  DOCS AUDIT: Skills changed but docs/SKILLS-MANIFEST.md was not updated."
    echo "   → Update SKILLS-MANIFEST.md with the new/changed skill entry"
    issues=$((issues + 1))
fi

# ── Check 3: New/changed scripts should update cortex-update.sh MAP ──
SCRIPTS_CHANGED=$(echo "$STAGED" | grep -c '^ops/scripts/' 2>/dev/null || true)
MAP_CHANGED=$(echo "$STAGED" | grep -c '^ops/scripts/cortex-update\\.sh$' 2>/dev/null || true)

if [[ "$SCRIPTS_CHANGED" -gt 0 && "$MAP_CHANGED" -eq 0 ]]; then
    # Only flag new scripts (not modifications to existing registered ones)
    NEW_SCRIPTS=$(echo "$STAGED" | grep '^ops/scripts/' | grep -v '^ops/scripts/cortex-update\\.sh$' | grep -v '__pycache__' || true)
    if [[ -n "$NEW_SCRIPTS" ]]; then
        echo "⚠️  DOCS AUDIT: New scripts staged but cortex-update.sh MAP was not updated."
        echo "   → Register new scripts in ops/scripts/cortex-update.sh using register()"
        issues=$((issues + 1))
    fi
fi

# ── Check 4: New service templates should be reflected in service layer docs ──
SERVICE_FILE_CHANGED=$(echo "$STAGED" | grep -c -E '(linux-service-layer|macos-service-layer)\.md$' 2>/dev/null || true)
TEMPLATE_SERVICE_CHANGED=$(echo "$STAGED" | grep -c '^docs/templates/.*\.service$' 2>/dev/null || true)
PLIST_CHANGED=$(echo "$STAGED" | grep -c '^docs/templates/.*\.plist$' 2>/dev/null || true)

if [[ "$TEMPLATE_SERVICE_CHANGED" -gt 0 && "$SERVICE_FILE_CHANGED" -eq 0 ]]; then
    echo "⚠️  DOCS AUDIT: New .service template added but linux-service-layer.md not updated."
    echo "   → Add the service to the fleet service map in docs/linux-service-layer.md"
    issues=$((issues + 1))
fi

if [[ "$PLIST_CHANGED" -gt 0 && "$SERVICE_FILE_CHANGED" -eq 0 ]]; then
    echo "⚠️  DOCS AUDIT: New .plist template added but macos-service-layer.md not updated."
    echo "   → Add the service to the fleet service map in docs/macos-service-layer.md"
    issues=$((issues + 1))
fi

# ── Exit with warning count ──
if [[ "$issues" -gt 0 ]]; then
    echo "───"
    echo "📋 DOCS AUDIT: $issues documentation issue(s) found."
    echo "   Fix them before committing, or use SKIP_DOC_AUDIT=1 to bypass."
    echo ""
    exit 0  # Warn only — does NOT block commit (blocking would be too disruptive)
fi
