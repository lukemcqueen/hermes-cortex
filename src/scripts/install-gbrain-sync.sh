#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — gbrain Sync Service (DEPRECATED)
# ─────────────────────────────────────────────────────────────
# sync-watch is obsolete. gbrain autopilot handles sync, extract,
# embed, lint, and backlinks internally every ~150s.
#
# To verify autopilot is running:
#   macOS: launchctl list com.gbrain.autopilot
#   Linux: systemctl --user status gbrain-autopilot
#
# If you need to restart the sync daemon:
#   macOS: launchctl kickstart gui/$(id -u)/com.gbrain.autopilot
#   Linux: systemctl --user restart gbrain-autopilot
# ─────────────────────────────────────────────────────────────

GREEN="${GREEN:-'\033[0;32m'}"; YELLOW="${YELLOW:-'\033[1;33m'}"; RESET="${RESET:-'\033[0m'}"
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }

warn "install-gbrain-sync.sh is deprecated — sync-watch has been removed."
info "  gbrain autopilot handles sync internally."
info "  To check: systemctl --user status gbrain-autopilot | grep Active"
exit 0