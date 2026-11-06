#!/usr/bin/env python3
"""ONE-RELEASE forwarding shim: cortex-doctor.py -> fleet-doctor.py (P3.cortex->fleet, 2026-11-06).

The doctor entrypoint was renamed to fleet-doctor.py (the canonical deploy
target). This shim keeps every legacy invocation working for one release —
live crons, documented commands, the deploy script's doctor runner, pi/other
host installers — by re-exec'ing its sibling under the new name. It must be
DELETED when the old name retires, along with its register() entry.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_NEW = os.path.join(_HERE, "fleet-doctor.py")

if not os.path.exists(_NEW):
    sys.stderr.write(
        f"cortex-doctor.py: forwarding target {_NEW} not found — deploy is "
        "incomplete (the one-release shim needs its fleet-doctor.py sibling).\n")
    sys.exit(3)

# Same interpreter, same argv, new program: the canonical re-exec pattern.
os.execv(sys.executable, [sys.executable, _NEW] + sys.argv[1:])
