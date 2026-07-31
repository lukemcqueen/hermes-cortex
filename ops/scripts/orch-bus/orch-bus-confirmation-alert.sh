#!/usr/bin/env bash
# orch-bus-confirmation-alert.sh — Wrapper for orch-bus-confirmation-poller.py report cron
# Produces a comprehensive bus health report every hour.
set -euo pipefail
exec python3 "$(dirname "$0")/orch-bus-confirmation-poller.py" report
