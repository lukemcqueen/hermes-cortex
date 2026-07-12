#!/usr/bin/env bash
set -euo pipefail

# ── Hermes Cortex — Version Bumper ─────────────────────────────
# Usage: bash ops/scripts/manage/bump-version.sh 1.1.0
# Effect: Updates VERSION, install.sh, README badges in both repos,
#         commits, tags, and pushes. Requires SSH access to both repos.

VERSION="${1:?Usage: bump-version.sh <semver> (e.g. 1.1.0)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRIVATE_DIR="$(cd "$SCRIPT_DIR/../hermes-cortex-private" 2>/dev/null && pwd || echo "")"

# Validate semver format (X.Y.Z)
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "Invalid version format: $VERSION — expected X.Y.Z (e.g. 1.1.0)"
  exit 1
fi

echo "=== Hermes Cortex v${VERSION} ==="

# ── Public repo ────────────────────────────────────────────
echo ""
echo "-> Public repo: hermes-cortex"
cd "$SCRIPT_DIR"

# Update VERSION file
echo "$VERSION" > VERSION
echo "  + VERSION -> $VERSION"

# Update install.sh
sed -i '' "s/^VERSION=\"[0-9.]*\"/VERSION=\"$VERSION\"/" install.sh
echo "  + install.sh VERSION -> $VERSION"

# Update README badge
sed -i '' "s/Version: [0-9.]*/Version: $VERSION/" README.md
sed -i '' "s/Version \`v[0-9.]*\`/Version \`v$VERSION\`/" README.md
echo "  + README.md badges -> $VERSION"

git add VERSION install.sh README.md
git commit -m "v${VERSION}: bump version"
git tag -a "v${VERSION}" -m "Hermes Cortex v${VERSION}"
git push origin main --tags
echo "  + Pushed to origin/main (tag: v${VERSION})"

# ── Private repo ────────────────────────────────────────────
if [[ -d "$PRIVATE_DIR" ]]; then
  echo ""
  echo "-> Private repo: hermes-cortex-private"
  cd "$PRIVATE_DIR"

  echo "$VERSION" > VERSION
  echo "  + VERSION -> $VERSION"

  sed -i '' "s/Version: [0-9.]*/Version: $VERSION/" README.md
  echo "  + README.md badge -> $VERSION"

  git add VERSION README.md
  git commit -m "v${VERSION}: bump version (align with public)"
  git tag -a "v${VERSION}" -m "Hermes Cortex Private v${VERSION}"
  git push origin main --tags
  echo "  + Pushed to origin/main (tag: v${VERSION})"
else
  echo ""
  echo "! Private repo not found at $PRIVATE_DIR — skipping"
fi

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "=== Hermes Cortex v${VERSION} released ==="
echo "  Public:  git@github.com:fleet-operator/hermes-cortex.git (v${VERSION})"
echo "  Private: git@github.com:fleet-operator/hermes-cortex-private.git (v${VERSION})"
