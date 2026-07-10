#!/bin/bash
# package-install.sh — Safe package installer with 14-day age gate.
#
# Usage:
#   pip-safe install requests flask==3.0.0
#   npm-safe install express
#   brew-safe install curl
#
# This wrapper checks every package's age before installing.
# If any package is younger than MIN_AGE_DAYS (default 14), the install
# is BLOCKED and the user is told how long to wait.
#
# To bypass (when you explicitly know the risk):
#   BYPASS_AGE_CHECK=1 pip-safe install brand-new-package

MIN_AGE_DAYS="${MIN_AGE_DAYS:-14}"
CHECKER="$HOME/.hermes-cortex/scripts/check-package-age.py"

if [ ! -f "$CHECKER" ]; then
    echo "🚨 Package age checker not found at $CHECKER"
    echo "   Install it or set BYPASS_AGE_CHECK=1 to skip."
    exit 1
fi

# ─── Parse manager from script name ───
SCRIPT_NAME=$(basename "$0")
case "$SCRIPT_NAME" in
    pip-safe|pip3-safe)     MANAGER="pip" ;;
    npm-safe)               MANAGER="npm" ;;
    brew-safe)              MANAGER="brew" ;;
    cargo-safe)             MANAGER="cargo" ;;
    *)
        # Fall back to first argument as manager if called generically
        if [ $# -ge 2 ]; then
            MANAGER="$1"
            shift
        else
            echo "Usage: pip-safe install <package> [package...]"
            echo "       npm-safe install <package> [package...]"
            echo "       brew-safe install <package> [package...]"
            exit 1
        fi
        ;;
esac

# ─── Parse subcommand ───
if [ $# -lt 1 ]; then
    echo "Usage: ${SCRIPT_NAME} install <package> [package...]"
    exit 1
fi

SUBCOMMAND="$1"
shift

if [ "$SUBCOMMAND" != "install" ] && [ "$SUBCOMMAND" != "add" ]; then
    # Not an install command — pass through directly
    # Resolve binary like the install path does
    case "$MANAGER" in
        pip)  REAL_BIN=$(which pip3 2>/dev/null || which pip 2>/dev/null || echo "/usr/local/bin/pip3") ;;
        npm)  REAL_BIN=$(which npm 2>/dev/null || echo "/usr/local/bin/npm") ;;
        brew) REAL_BIN=$(which brew 2>/dev/null || echo "/usr/local/bin/brew") ;;
        cargo) REAL_BIN=$(which cargo 2>/dev/null || echo "/usr/local/bin/cargo") ;;
    esac
    exec "$REAL_BIN" "$SUBCOMMAND" "$@"
fi

PACKAGES=("$@")
if [ ${#PACKAGES[@]} -eq 0 ]; then
    echo "No packages specified."
    exit 1
fi

# ─── Check each package age ───
if [ -z "$BYPASS_AGE_CHECK" ]; then
    echo "🔒 Checking package ages (min ${MIN_AGE_DAYS}d since publication)..."
    if ! python3 "$CHECKER" --min-days "$MIN_AGE_DAYS" "$MANAGER" "${PACKAGES[@]}"; then
        echo ""
        echo "🛑 INSTALL BLOCKED — One or more packages are too new."
        echo "   This protects against recently published supply-chain attacks."
        echo "   To bypass: BYPASS_AGE_CHECK=1 ${SCRIPT_NAME} install ${PACKAGES[*]}"
        exit 1
    fi
    echo ""
    echo "✅ All packages pass age check. Proceeding with install..."
else
    echo "⚠️  Age check bypassed (BYPASS_AGE_CHECK=1)"
fi

# ─── Run the real install ───
# Find the real binary (resolve aliases, use direct paths)
REAL_BIN=""
case "$MANAGER" in
    pip)  REAL_BIN=$(which pip3 2>/dev/null || which pip 2>/dev/null || echo "/usr/local/bin/pip3") ;;
    npm)  REAL_BIN=$(which npm 2>/dev/null || echo "/usr/local/bin/npm") ;;
    brew) REAL_BIN=$(which brew 2>/dev/null || echo "/usr/local/bin/brew") ;;
    cargo) REAL_BIN=$(which cargo 2>/dev/null || echo "/usr/local/bin/cargo") ;;
esac

if [ ! -x "$REAL_BIN" ]; then
    echo "❌ Cannot find '$MANAGER' binary. Tried: $REAL_BIN"
    echo "   Install it first or update the path in this script."
    exit 1
fi

exec "$REAL_BIN" "$SUBCOMMAND" "${PACKAGES[@]}"
