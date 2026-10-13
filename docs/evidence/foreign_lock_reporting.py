#!/usr/bin/env python3
"""Show that a bare `check_lock` reports a lock owned by ANOTHER session.

Hermetic by necessity. A foreign lock cannot honestly be produced in the live state
dir — hand-writing a lock file is a governance violation — so this points the
module's `GOVERNANCE_STATE_DIR` at a throwaway directory, writes one there, and asks
the DEPLOYED server the same question an operator would ask with no session id:

    python3 docs/evidence/foreign_lock_reporting.py   # exit 0 = reported; 1 = not; 3 = could not verify

The code path is the one that runs in production: `_live_locks()` reads whatever
`GOVERNANCE_STATE_DIR` names, and `_check_lock` reports its result. Covered by
`tests/test_lock_truth.py::test_a_foreign_live_lock_is_reported` as well.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

CANDIDATES = [
    Path.home() / ".hermes-cortex/scripts/loop-gov-mcp.py",
    Path.home() / ".hermes-cortex/tools/loop-governance/loop-gov-mcp.py",
    Path(__file__).resolve().parent.parent / "mcp-servers/loop-gov-mcp.py",
]


def main() -> int:
    src = next((p for p in CANDIDATES if p.exists()), None)
    if src is None:
        print("COULD NOT VERIFY — no loop-gov-mcp.py at any candidate path")
        return 3

    spec = importlib.util.spec_from_file_location("loop_gov_deployed", src)
    if spec is None or spec.loader is None:
        print("COULD NOT VERIFY — could not load the server module")
        return 3
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print(f"module: {src}")

    with tempfile.TemporaryDirectory() as td:
        mod.GOVERNANCE_STATE_DIR = Path(td)
        (Path(td) / ".governance-sess_FOREIGN.json").write_text(json.dumps({
            "task_id": "kustos-some-other-task",
            "session_id": "sess_FOREIGN",
            "agent": "kustos",
            "status": "executing",
            "heartbeat_at": "2099-01-01T00:00:00Z",
            "ttl_seconds": 3600,
            "repo_slug": "koscap-mwi",
            "repo_path": "/home/app/mwi/koscap-mwi",
        }))
        got = json.loads(mod._check_lock({}).content[0].text)
        print("a bare check_lock whose own session is NOT the lock's owner:")
        print(json.dumps({k: got[k] for k in ("active", "live_lock_count")}, indent=2))
        print("locks:", json.dumps(got["locks"], indent=2))
        found = any(l["session_id"] == "sess_FOREIGN" for l in got["locks"])
        print("a foreign session's live lock is reported:", found)

    print("temp state dir removed — no real lock file was created, read or changed")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
