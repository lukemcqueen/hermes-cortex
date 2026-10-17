#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# consolidate-env.sh — single .env source of truth (cortex layer)
#
# Merges the legacy bus config file (~/.hermes-cortex/cortex-bus.conf) into
# the single cortex env file (~/hermes-cortex/.env), then creates
# ~/.hermes-cortex/.env as a SYMLINK to it so every existing reader keeps
# working (doctor, forwarder, failover watchdog, contact-orchestrator, ...).
# The legacy cortex-bus.conf name is retired: a host that still carries it
# (real file or old symlink) is migrated to the .env name.
#
#   ⚠ ~/.hermes/.env (Hermes Agent runtime) is NEVER touched — it is
#     Hermes-owned (provider API keys, Telegram, browser/terminal
#     settings). This script refuses to operate on it.
#
# Idempotent: already-consolidated hosts exit 0 with no changes.
# Safe: backs up the legacy conf before replacing; aborts on value conflicts.
# Platforms: Linux + macOS (no bash-4-only features).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ENV="${HOME}/hermes-cortex/.env"           # the canonical cortex env
DEPLOY_ENV="${HOME}/.hermes-cortex/.env"        # the sanctioned back-compat symlink (deploy dir)
LEGACY="${HOME}/.hermes-cortex/cortex-bus.conf" # retired name — migrated to DEPLOY_ENV
BACKUP="${LEGACY}.bak-$(date +%Y%m%d)"

info() { printf '✓ %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }
fail() { printf '✗ %s\n' "$*" >&2; exit 1; }

get_val() { # <file> <key> → value (empty if absent)
  grep -E "^${2}=" "$1" 2>/dev/null | head -1 | cut -d= -f2- || true
}

# ── Guard 1: never touch the Hermes runtime env ───────────────
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1 || CHECK_ONLY=0

# ── Already consolidated? ────────────────────────────────────
if [[ -L "${DEPLOY_ENV}" ]]; then
  target="$(readlink "${DEPLOY_ENV}" 2>/dev/null || true)"
  if [[ "${target}" == "${REPO_ENV}" ]]; then
    # A leftover retired-name symlink is inert (same inode) — drop it.
    if [[ -e "${LEGACY}" ]] || [[ -L "${LEGACY}" ]]; then rm -f "${LEGACY}" 2>/dev/null || true; fi
    info "already consolidated: ${DEPLOY_ENV} → ${REPO_ENV}"
    exit 0
  fi
  fail "${DEPLOY_ENV} is a symlink to ${target}, not ${REPO_ENV} — refusing to touch"
fi

# Seed the canonical env from the legacy conf when it does not exist yet —
# hosts installed before the single-env refactor otherwise break, since every
# script now reads ${REPO_ENV}. (Never overwrite an existing canonical env.)
if [[ ! -f "${REPO_ENV}" ]]; then
  if [[ -f "${LEGACY}" && ! -L "${LEGACY}" ]]; then
    cp "${LEGACY}" "${REPO_ENV}"
    chmod 600 "${REPO_ENV}"
    info "seeded ${REPO_ENV} from ${LEGACY} (migration)"
  else
    fail "neither ${REPO_ENV} nor ${LEGACY} exists — run install.sh first"
  fi
fi

# ── Guard 2: a stray real-file .env in the deploy dir ────────
# Historically ~/.hermes-cortex/.env was a stray symlink to ~/langfuse/.env.
# The .env name is now OURS (canonical + sanctioned symlink), so a REAL file
# at the deploy path is not something consolidate-env created — refuse to own it.
if [[ -e "${DEPLOY_ENV}" && ! -L "${DEPLOY_ENV}" ]]; then
  fail "${DEPLOY_ENV} is a real file (not a symlink) — refuse to replace unowned data"
fi

# ── Collect legacy vars missing from the target (conflict-safe) ─
missing_keys=()
missing_vals=()
if [[ -f "${LEGACY}" && ! -L "${LEGACY}" ]]; then
  while IFS= read -r line; do
    [[ "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
    key="${line%%=*}"
    val="${line#*=}"
    existing="$(get_val "${REPO_ENV}" "${key}")"
    if [[ -n "${existing}" ]]; then
      if [[ "${existing}" != "${val}" ]]; then
        fail "CONFLICT on ${key}: ${REPO_ENV} has '${existing}', ${LEGACY} has '${val}' — no changes made"
      fi
      continue  # same value — nothing to merge
    fi
    missing_keys+=("${key}")
    missing_vals+=("${val}")
  done < "${LEGACY}"
fi

if [[ "${CHECK_ONLY}" == "1" ]]; then
  if [[ ${#missing_keys[@]} -eq 0 ]]; then
    info "check: ${LEGACY} fully represented in ${REPO_ENV}"
  else
    warn "check: ${#missing_keys[@]} var(s) in ${LEGACY} missing from ${REPO_ENV}: ${missing_keys[*]}"
    exit 1
  fi
  exit 0
fi

# ── Merge ────────────────────────────────────────────────────
if [[ ${#missing_keys[@]} -gt 0 ]]; then
  {
    echo ""
    echo "# ── Merged from ${LEGACY} by consolidate-env.sh ($(date +%F)) ──"
    for i in "${!missing_keys[@]}"; do
      echo "${missing_keys[$i]}=${missing_vals[$i]}"
    done
  } >> "${REPO_ENV}"
  info "merged ${#missing_keys[@]} var(s): ${missing_keys[*]}"
else
  info "no new vars in ${LEGACY} — only the symlink step remains"
fi

# ── Create the sanctioned .env symlink ───────────────────────
rm -f "${DEPLOY_ENV}" 2>/dev/null || true
ln -s "${REPO_ENV}" "${DEPLOY_ENV}"

# ── Retire the legacy name (real files get a backup first) ──
if [[ -e "${LEGACY}" || -L "${LEGACY}" ]]; then
  if [[ -f "${LEGACY}" && ! -L "${LEGACY}" ]]; then
    cp "${LEGACY}" "${BACKUP}" 2>/dev/null || warn "could not back up ${LEGACY} to ${BACKUP}"
  fi
  rm -f "${LEGACY}" 2>/dev/null || true
fi

info "${DEPLOY_ENV} → ${REPO_ENV} (cortex-bus.conf retired)"
if [[ -f "${BACKUP}" ]]; then
  info "legacy backup kept at ${BACKUP}"
fi
info "~/.hermes/.env (Hermes runtime) untouched by design — it stays Hermes-owned."