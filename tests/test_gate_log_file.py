#!/usr/bin/env python3
"""The gate keeps its own bounded log under the CORTEX tree (not only Hermes's).

Luke 2026-10-02: gate decisions — adversarial review, refutation, triage — only
existed in ~/.hermes/logs/mcp-stderr.log, which is Hermes's capture of the MCP
server's stderr: outside our tree, and subject to Hermes's rotation.

Runs each case in a SUBPROCESS: the handler is installed at import, and loading
the module twice in one process would stack handlers on the same logger name.

Run: python3 tests/test_gate_log_file.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_FAIL = []

SNIPPET = '''
import importlib.util, os, sys
from pathlib import Path
REPO = Path({repo!r})
spec = importlib.util.spec_from_file_location("loop_gov_mcp", REPO / "mcp-servers/loop-gov-mcp.py")
if spec is None or spec.loader is None:
    sys.exit("cannot load")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)          # may raise -> non-fatal fallback must prevent that
mcp.log.warning("GATE-LOG-MARKER-9f3a")
for h in mcp.log.handlers:
    try:
        h.flush()
    except Exception:
        pass
logfile = Path(os.environ["CORTEX_DEPLOY_HOME"]) / "logs" / "loop-governance.log"
text = logfile.read_text() if logfile.is_file() else ""
print("IMPORT_OK")
print("FILE_EXISTS", logfile.is_file())
print("MARKER_IN_FILE", "GATE-LOG-MARKER-9f3a" in text)
'''


def _run(deploy_home: str) -> subprocess.CompletedProcess:
    import os
    env = dict(os.environ)
    env["CORTEX_DEPLOY_HOME"] = deploy_home
    return subprocess.run([sys.executable, "-c", SNIPPET.format(repo=str(REPO))],
                          capture_output=True, text=True, timeout=120, env=env)


def _check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _FAIL.append(label)


def test_log_file():
    with tempfile.TemporaryDirectory() as td:
        r = _run(td)
        _check("the module imports with the file handler installed", "IMPORT_OK" in r.stdout,
               (r.stderr or "")[-300:])
        _check("the cortex log file is created", "FILE_EXISTS True" in r.stdout, r.stdout)
        _check("a gate log line lands in the CORTEX log, not only Hermes's",
               "MARKER_IN_FILE True" in r.stdout, r.stdout)
        _check("stderr logging still happens too (harness capture unchanged)",
               "GATE-LOG-MARKER-9f3a" in (r.stderr or ""), (r.stderr or "")[-200:])

    # The control: an unusable log location must NOT break the gate. /dev/null/x
    # cannot be created as a directory.
    r = _run("/dev/null/nope")
    _check("an unusable log dir does not break the module (non-fatal fallback)",
           "IMPORT_OK" in r.stdout, (r.stderr or "")[-400:])
    _check("the gate still logs to stderr in that case",
           "GATE-LOG-MARKER-9f3a" in (r.stderr or ""), (r.stderr or "")[-200:])


if __name__ == "__main__":
    print("Gate log — cortex-owned record")
    test_log_file()
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        sys.exit(1)
    print("ALL PASS")
