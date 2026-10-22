#!/usr/bin/env python3
"""
cortex-doctor.py — Hermes Cortex installation health check

Like 'brew doctor' for Hermes Cortex: single command that checks
and fixes your entire installation — repo, crons, scripts,
services, system, config, governance (MCP servers, hooks), and
install footprint.

This is now a thin wrapper around the cortex_doctor package.

Usage:
    python3 cortex-doctor.py                  # full check (default)
    python3 cortex-doctor.py --json           # machine-readable output
    python3 cortex-doctor.py --fix            # auto-fix everything
    python3 cortex-doctor.py --watch          # re-check every 30s
    python3 cortex-doctor.py --quiet          # compact output
    python3 cortex-doctor.py --bus-alert      # send bus messages for actionable issues

Exit codes: 0 = pass   1 = warn   2 = fail
"""

import importlib.util
import os
import subprocess
import sys

# Ensure the package directory AND the scripts parent are on the path.
# This handles both deployment (~/.hermes-cortex/scripts/) and in-repo
# (ops/scripts/manage/) layouts so that hermes_paths and lib.cortex_bus
# are importable regardless of CWD.
_this_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_dir = os.path.join(_this_dir, "cortex_doctor")
if os.path.isdir(_pkg_dir):
    if _this_dir not in sys.path:
        sys.path.insert(0, _this_dir)
    # In-repo case: hermes_paths.py lives in ops/scripts/ (parent of manage/)
    _parent = os.path.dirname(_this_dir)
    _hermes_paths = os.path.join(_parent, "hermes_paths.py")
    if os.path.exists(_hermes_paths) and _parent not in sys.path:
        sys.path.insert(0, _parent)


# ── Run under an interpreter that can import the declared dependency set ──────
#
# The doctor is documented as `python3 cortex-doctor.py`, and on a fleet host
# `python3` is whatever the agent's session happens to have on PATH. Measured
# 2026-10-22 on esther: that is the Hermes runtime venv
# (~/.hermes/installs/<id>/environments/<id>/venv/bin/python3), which cannot
# import yaml. The FLEET venv has it — `fix-cortex-venv.py --check` reports all 6
# declared requirements satisfied — the doctor simply never used it.
#
# Every yaml-dependent check then ran WEAKER than it reported and nothing said so:
# the skills manifest fell back to a substring scan, and check_skills_loadable
# dropped to text mode. A doctor that quietly checks less than it claims is worse
# than one that refuses, because the operator reads a clean report and believes it.
#
# So resolve a capable interpreter and re-exec ONCE. If no capable interpreter
# exists the doctor still runs — degraded, and each check that degrades SAYS so —
# because a host whose venv is broken must still be diagnosable by the tool that
# repairs it (`fix-cortex-venv.py`).
DECLARED_MODULES = ("yaml", "mcp")
REEXEC_FLAG = "CORTEX_DOCTOR_REEXEC"


def _can_import_here(name):
    """Can THIS interpreter import `name`? (find_spec can raise, so guard it.)"""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _child_imports_all(py, mods=DECLARED_MODULES):
    """Probe a CHILD interpreter, in a CLEAN environment.

    `env -u PYTHONPATH -u PYTHONHOME` is the point, not decoration: an inherited
    PYTHONPATH puts a foreign site-packages ahead of the target venv's own, so a
    capable interpreter reads as broken (or a bare python as capable) and the
    decision is made about the caller's environment instead of the candidate.
    """
    try:
        return subprocess.run(
            ["env", "-u", "PYTHONPATH", "-u", "PYTHONHOME", py, "-c",
             "import " + ", ".join(mods)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def candidate_interpreters():
    """Interpreters to try, in preference order, excluding the current one.

    `CORTEX_PYTHON` is the host's own declaration (written by cortex-update.sh
    into ~/.hermes-cortex/agent.env) and wins — an operator who points it
    somewhere else must not be overruled. The fleet venv is the fallback, and a
    `PYTHON=`-style override is deliberately NOT invented here: one declaration
    per host is the rule.
    """
    declared = os.environ.get("CORTEX_PYTHON", "")
    if not declared:
        env_file = os.path.join(os.path.expanduser("~"), ".hermes-cortex", "agent.env")
        try:
            with open(env_file) as fh:
                for line in fh:
                    if line.startswith("CORTEX_PYTHON="):
                        declared = line.split("=", 1)[1].strip()
                        break
        except OSError:
            pass
    fleet = os.path.join(os.path.expanduser("~"), ".hermes-cortex", "venv", "bin", "python3")
    current = os.path.realpath(sys.executable)
    out = []
    for cand in (declared, fleet):
        if not cand or not os.path.isfile(cand):
            continue
        if os.path.realpath(cand) == current:
            continue
        if cand not in out:
            out.append(cand)
    return out


def choose_interpreter(current_ok, candidates, probe):
    """Which interpreter the doctor should run under, or None to stay put.

    A PURE decision with injected probes, so both directions are testable without
    a second python on the box: `current_ok` says whether the running interpreter
    already has the declared set, and `probe(path)` says whether a candidate does.
    """
    if current_ok:
        return None
    for cand in candidates:
        if probe(cand):
            return cand
    return None


def reexec_if_degraded():
    """Re-exec under a capable interpreter once; otherwise warn and carry on."""
    if os.environ.get(REEXEC_FLAG) == "1":
        return None
    current_ok = all(_can_import_here(m) for m in DECLARED_MODULES)
    chosen = choose_interpreter(current_ok, candidate_interpreters(), _child_imports_all)
    if chosen:
        os.environ[REEXEC_FLAG] = "1"
        os.execv(chosen, [chosen, os.path.abspath(__file__)] + sys.argv[1:])
    if not current_ok:
        sys.stderr.write(
            "cortex-doctor: running under %s, which cannot import %s — the checks "
            "that depend on them will be WEAKER than reported and will say so.\n"
            "  repair: python3 ops/scripts/manage/fix-cortex-venv.py\n"
            "  or run: ~/.hermes-cortex/venv/bin/python3 %s\n"
            % (sys.executable, ", ".join(DECLARED_MODULES), os.path.abspath(__file__)))
    return None


if __name__ == "__main__":
    reexec_if_degraded()
    from cortex_doctor.cli import main
    main()
