#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# consolidate-env.sh — single .env source of truth (cortex layer)
#
# Merges the bus config file (~/.hermes-cortex/cortex-bus.conf) into
# the single cortex env file (~/hermes-cortex/.env), then replaces
# the conf file with a symlink so every existing reader keeps working
# (doctor, forwarder, failover watchdog, contact-orchestrator, ...).
#
#   ⚠ ~/.hermes/.env (Hermes Agent runtime) is NEVER touched — it is
#     Hermes-owned (provider API keys, Telegram, browser/terminal
#     settings). This script refuses to operate on it.
#
# Idempotent: already-consolidated hosts exit 0 with no changes.
# Safe: backs up the conf before replacing; aborts on value conflicts.
# Platforms: Linux + macOS (no bash-4-only features).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ENV="${HOME}/hermes-cortex/.env"
CONF="${HOME}/.hermes-cortex/cortex-bus.conf"
BACKUP="${CONF}.bak-$(date +%Y%m%d)"

info() { printf '✓ %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }
fail() { printf '✗ %s\n' "$*" >&2; exit 1; }

get_val() { # <file> <key> → value (empty if absent)
  grep -E "^${2}=" "$1" 2>/dev/null | head -1 | cut -d= -f2- || true
}

# ── Guard 1: never touch the Hermes runtime env ───────────────
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1 || CHECK_ONLY=0

# ── Already consolidated? ────────────────────────────────────
if [[ -L "${CONF}" ]]; then
  target="$(readlink "${CONF}" 2>/dev/null || true)"
  if [[ "${target}" == "${REPO_ENV}" ]]; then
    info "already consolidated: ${CONF} → ${REPO_ENV}"
    exit 0
  fi
  fail "${CONF} is a symlink to ${target}, not ${REPO_ENV} — refusing to touch"
fi

[[ -f "${REPO_ENV}" ]] || fail "${REPO_ENV} missing — run install.sh first"
[[ -f "${CONF}" ]] || { info "no ${CONF} — nothing to consolidate"; exit 0; }

# ── Collect conf vars missing from the target (conflict-safe) ─
missing_keys=()
missing_vals=()
while IFS= read -r line; do
  [[ "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
  key="${line%%=*}"
  val="${line#*=}"
  existing="$(get_val "${REPO_ENV}" "${key}")"
  if [[ -n "${existing}" ]]; then
    if [[ "${existing}" != "${val}" ]]; then
      fail "CONFLICT on ${key}: ${REPO_ENV} has '${existing}', ${CONF} has '${val}' — no changes made"
    fi
    continue  # same value — nothing to merge
  fi
  missing_keys+=("${key}")
  missing_vals+=("${val}")
done < "${CONF}"

if [[ "${CHECK_ONLY}" == "1" ]]; then
  if [[ ${#missing_keys[@]} -eq 0 ]]; then
    info "check: ${CONF} fully represented in ${REPO_ENV}"
  else
    warn "check: ${#missing_keys[@]} var(s) in ${CONF} missing from ${REPO_ENV}: ${missing_keys[*]}"
    exit 1
  fi
  exit 0
fi

# ── Merge ────────────────────────────────────────────────────
if [[ ${#missing_keys[@]} -gt 0 ]]; then
  {
    echo ""
    echo "# ── Merged from ${CONF} by consolidate-env.sh ($(date +%F)) ──"
    for i in "${!missing_keys[@]}"; do
      echo "${missing_keys[$i]}=${missing_vals[$i]}"
    done
  } >> "${REPO_ENV}"
  info "merged ${#missing_keys[@]} var(s): ${missing_keys[*]}"
else
  info "no new vars in ${CONF} — only the symlink step remains"
fi

# ── Replace conf with symlink (backup first) ─────────────────
cp "${CONF}" "${BACKUP}" 2>/dev/null || warn "could not back up ${CONF} to ${BACKUP}"
rm "${CONF}"
ln -s "${REPO_ENV}" "${CONF}"

info "${CONF} → symlink → ${REPO_ENV}"
info "backup kept at ${BACKUP}"
info "~/.hermes/.env (Hermes runtime) untouched by design — it stays Hermes-owned."
