#!/usr/bin/env bash
# bus-message-tracker-alert.sh — Wrapper for bus-message-tracker.py report cron
# Produces a comprehensive bus health report every hour.
set -euo pipefail
exec python3 "$(dirname "$0")/orch-bus-message-tracker.py" report
