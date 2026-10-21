#!/usr/bin/env python3
"""Repair ~/.hermes-cortex/venv on ANY host — one command, verified by import.

WHY THIS EXISTS. `~/.hermes-cortex/venv` is the fleet venv (cortex-update.sh registers every
MCP server against it), but nothing declared what it should CONTAIN, so a host whose venv was
empty or partial could only be fixed by someone reading the source to work out the
dependencies. Found the hard way on esther: the venv could not collect a test module (no
fastapi) and had no pytest, while the resolver quietly used the Hermes venv instead — the
tree we are migrating away from.

WHAT IT DOES
  * reads the DECLARED set from ops/install/requirements.txt (this repo, or --requirements);
  * decides what is missing by IMPORTING it in the target interpreter — never by metadata or
    exit codes ("PyYAML" is a distribution name; `yaml` is the module);
  * ALSO probes each declared CAPABILITY the import cannot prove (CAPABILITY_PROBES below).
    An importable module can still be too old for the call sites that use it — measured on
    gisu 2026-10-20, where mcp imported fine and rejected the 2.0 constructor handlers the
    fleet's MCP servers are built on, so "ok: imports all 6 requirements" was printed on a
    host whose governance gate was dead. Such a requirement is reported INCOMPATIBLE, and
    counted as a gap, so --check (and cortex-update.sh, which gates its install on it) sees it;
  * installs only the missing ones, preferring `uv` and falling back to the venv's own pip
    (a uv venv has NO pip until `ensurepip` runs — handled);
  * re-checks by import afterwards and fails loudly if the venv still cannot import them.

USAGE
  python3 fix-cortex-venv.py                    # repair the default venv
  python3 fix-cortex-venv.py --check            # report only; exit 3 if anything is missing
  python3 fix-cortex-venv.py --check --json     # last line is JSON, for a doctor/deploy hook
  python3 fix-cortex-venv.py --venv /path/to/venv --requirements /path/to/requirements.txt

EXIT CODES
  0  the venv can import everything declared (repaired if it could not)
  1  repair attempted and the venv STILL cannot import something (the message says what)
  2  usage error
  3  --check found gaps, or the venv is absent/unusable — COULD NOT VERIFY. Never a pass.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_VENV = "~/.hermes-cortex/venv"
#: Distribution name -> module name, where they differ. Importing "PyYAML" is not a thing.
MODULE_ALIASES = {"pyyaml": "yaml", "pillow": "PIL", "psycopg2-binary": "psycopg2",
                  "python-dateutil": "dateutil", "beautifulsoup4": "bs4"}

#: Import each module in the TARGET interpreter and report per module. Modules arrive as
#: ARGV (never interpolated into this string).
PROBE = (
    "import importlib, json, sys\n"
    "out = {}\n"
    "for m in sys.argv[1:]:\n"
    "    try:\n"
    "        importlib.import_module(m)\n"
    "        out[m] = True\n"
    "    except Exception:\n"
    "        out[m] = False\n"
    "print(json.dumps(out))\n"
)


def parse_requirements(text):
    """Requirement lines, comments and blanks stripped, order kept."""
    out = []
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def dist_name(req):
    """'psycopg[binary]>=3.1' -> 'psycopg'."""
    name = req.split("[", 1)[0]
    for sep in (">=", "<=", "==", "~=", ">", "<", "!", " "):
        name = name.split(sep, 1)[0]
    return name.strip()


def module_for(req):
    """The module to import for a requirement ('PyYAML>=6.0' -> 'yaml')."""
    name = dist_name(req)
    alias = MODULE_ALIASES.get(name.lower())
    if alias:
        return alias
    return name.replace("-", "_")


#: Capabilities IMPORTABILITY CANNOT PROVE, keyed by DISTRIBUTION name (lowercase).
#:
#: A module can import perfectly and still be unusable by the call sites that use it. The
#: fleet's MCP servers register their handlers through the mcp 2.0 constructor API, which
#: the 1.x SDK rejects at runtime — so `--check` said "ok" on a host whose governance CLI
#: exited 3 on every write gate, and cortex-update.sh, which gates its repair on that same
#: check, therefore never installed anything (measured: gisu, 2026-10-20). A failed probe
#: is reported as INCOMPATIBLE, never as "missing", so the message names the real fault.
#:
#: Each probe runs in the TARGET interpreter, as argv-free source, with the same clean
#: environment as the import probe. Code, not a version string: version metadata is a
#: second source of truth that drifts from what the interpreter can actually do.
CAPABILITY_PROBES = {
    "mcp": {
        "requires": ("the 2.0 constructor API "
                     "(Server(name, on_list_tools=..., on_call_tool=...))"),
        "probe": ("from mcp.server import Server\n"
                  "Server('_cortex_capability_probe',\n"
                  "       on_list_tools=None, on_call_tool=None)\n"),
    },
}


def capability_gap(python, req):
    """Why `req` is unusable even though it imports, or None when it is fine.

    Returns None for a requirement that declares no probe — an absent declaration is not a
    failure, and inventing a check for a module that needs none is how a checker becomes
    noise. A probe that cannot RUN (no interpreter, timeout) is reported as a gap too: a
    check that could not be performed is not a pass.
    """
    declared = CAPABILITY_PROBES.get(dist_name(req).lower())
    if not declared:
        return None
    try:
        proc = subprocess.run([str(python), "-c", declared["probe"]], capture_output=True,
                              text=True, timeout=120, env=target_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"could not run the capability probe: {exc}"
    if proc.returncode == 0:
        return None
    detail = [ln.strip() for ln in (proc.stderr or proc.stdout or "").splitlines() if ln.strip()]
    return f"needs {declared['requires']} — {detail[-1] if detail else 'probe failed'}"


#: Names removed from the target's environment by :func:`target_env`, for reporting.
_STRIPPED_ENV: list[str] = []


def target_env():
    """Environment for probing/installing INTO the target venv.

    An inherited PYTHONPATH is a hazard, not a nicety. Measured on esther 2026-10-13: the
    agent runtime exports
    PYTHONPATH=$HOME/.hermes/installs/<id>/environments/<id>/venv/lib/python3.14/site-packages
    which lands AHEAD of the venv's own site-packages, so `import mcp` inside the FLEET venv
    loaded a python3.14 copy under a 3.12 interpreter and died on
    ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'. The venv was healthy —
    the PROBE was contaminated — and it reported "still cannot import" about a venv that
    imports fine. The deploy inherited the same false failure.

    A venv's correctness must not depend on the caller's environment, so the probe and the
    install run with PYTHONPATH/PYTHONHOME removed. The caller is then TOLD what was ignored:
    a silently-dropped variable is how this stayed invisible.
    """
    env = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME"):
        if env.pop(name, None) is not None and name not in _STRIPPED_ENV:
            _STRIPPED_ENV.append(name)
    return env


def _import_diagnosis(python, reqs):
    """WHY an import failed: the exception, and where a working import loaded from.

    "still cannot import" cannot distinguish absence from the real causes — an ABI mismatch, a
    shadowing path, a broken binary — and the traceback names them. So print it.
    """
    mods = sorted({module_for(r) for r in reqs})
    code = (
        "import importlib, sys, traceback\n"
        "for m in sys.argv[1:]:\n"
        "    try:\n"
        "        mod = importlib.import_module(m)\n"
        "        print('loaded', m, 'from', getattr(mod, '__file__', '?'))\n"
        "    except Exception as exc:\n"
        "        tb = traceback.format_exc().strip().splitlines()\n"
        "        print('failed', m, type(exc).__name__, exc)\n"
        "        if len(tb) > 1:\n"
        "            print('  at', tb[-2].strip())\n"
    )
    try:
        proc = subprocess.run([str(python), "-c", code, *mods], capture_output=True, text=True,
                              timeout=180, env=target_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"  could not diagnose with {python}: {exc}"]
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return [f"  (no diagnosis output) {(proc.stderr or '').strip()[:200]}"]
    return [f"  {ln}" for ln in lines[:6]]


def venv_state(python, requirements):
    """{requirement: importable?} using the TARGET interpreter, in a CLEAN environment."""
    modules = {}
    for req in requirements:
        modules.setdefault(module_for(req), []).append(req)
    try:
        proc = subprocess.run([str(python), "-c", PROBE, *sorted(modules)], capture_output=True,
                              text=True, timeout=180, env=target_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"could not run {python}: {exc}") from None
    try:
        probed = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise SystemExit(f"{python} produced no probe output:\n{proc.stdout}{proc.stderr}") from None
    state = {}
    for module, reqs in modules.items():
        for req in reqs:
            state[req] = bool(probed.get(module))
    return state


def find_requirements(start):
    """The declared set, from the repo layout OR the deployed one.

    Deployed: <deploy-home>/scripts/fix-cortex-venv.py -> <deploy-home>/install/requirements.txt
    Repo:     ops/scripts/manage/fix-cortex-venv.py    -> ops/install/requirements.txt
    A fixed number of `..` cannot serve both, so search upward for either shape.
    """
    p = Path(start).resolve()
    for parent in [p.parent, *p.parents]:
        for cand in (parent / "install" / "requirements.txt",
                     parent / "ops" / "install" / "requirements.txt"):
            if cand.is_file():
                return cand
    return None


def fix_argv(venv, requirements=None):
    argv = [sys.executable, str(Path(__file__).resolve()), "--venv", str(venv)]
    if requirements is not None:
        argv += ["--requirements", str(requirements)]
    return argv


def create_venv_cmd(venv):
    return f"python3 -m venv {venv}"


def _installer(venv_python, reqs):
    """An install command that works on a host with uv, pip, or NEITHER (ensurepip first)."""
    if shutil.which("uv"):
        return ["uv", "pip", "install", "--python", str(venv_python), *reqs]
    probe = subprocess.run([str(venv_python), "-c", "import pip"], capture_output=True)
    if probe.returncode != 0:
        subprocess.run([str(venv_python), "-m", "ensurepip", "--upgrade"], capture_output=True)
    return [str(venv_python), "-m", "pip", "install", *reqs]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Repair the fleet python venv, verified by import.")
    ap.add_argument("--venv", default=DEFAULT_VENV, help=f"venv root (default {DEFAULT_VENV})")
    ap.add_argument("--requirements", default=None,
                    help="declared dependency set (default: the requirements.txt beside this "
                         "script's install/ directory, repo or deployed layout)")
    ap.add_argument("--check", action="store_true", help="report only; change nothing")
    ap.add_argument("--json", action="store_true", help="last line is machine-readable JSON")
    args = ap.parse_args(argv)

    venv = Path(args.venv).expanduser()
    # Resolve the declared set for EITHER layout (repo or deployed) unless told explicitly.
    reqs_path = (Path(args.requirements).expanduser() if args.requirements
                 else find_requirements(__file__) or Path("ops/install/requirements.txt"))
    python = venv / "bin" / "python3"
    report = {"venv": str(venv), "python": str(python), "venv_ok": venv.is_dir(),
              "requirements": str(reqs_path), "missing": [], "present": [],
              "incompatible": {}, "repaired": False}

    def emit(code, human_lines):
        lines = list(human_lines)
        if _STRIPPED_ENV:
            # Say what was ignored rather than dropping it quietly: a silently-removed variable
            # is how the contaminated probe stayed invisible and the VENV took the blame.
            lines.insert(0, f"note: ignored inherited {' '.join(_STRIPPED_ENV)} while probing "
                            f"{venv} — an inherited python path can shadow the venv's own "
                            f"packages and make a healthy venv look broken")
        for line in lines:
            print(line)
        if args.json:
            report["fix_argv"] = fix_argv(venv, reqs_path)
            report["ignored_env"] = list(_STRIPPED_ENV)
            print(json.dumps(report))
        return code

    if not reqs_path.is_file():
        report["venv_ok"] = venv.is_dir()
        return emit(3, [f"COULD NOT VERIFY — no declared dependency set at {reqs_path}",
                        "  pass --requirements, or restore ops/install/requirements.txt"])
    requirements = parse_requirements(reqs_path.read_text())
    if not requirements:
        return emit(3, [f"COULD NOT VERIFY — {reqs_path} declares nothing"])

    if not python.exists():
        return emit(3, [f"the venv is absent or unusable: {python}",
                        f"  create it:  {create_venv_cmd(venv)}",
                        f"  then:      {' '.join(fix_argv(venv, reqs_path))}"])

    state = venv_state(python, requirements)
    report["present"] = [r for r, ok in state.items() if ok]
    report["missing"] = [r for r, ok in state.items() if not ok]
    # An importable requirement can still be UNUSABLE by the code that calls it, so the
    # capabilities the import cannot prove are probed. Only the importable ones: a module
    # that is absent has no capability to check.
    report["incompatible"] = {}
    for req in report["present"]:
        why = capability_gap(python, req)
        if why:
            report["incompatible"][req] = why
    gaps = report["missing"] + list(report["incompatible"])
    cmd = " ".join(fix_argv(venv, reqs_path))

    def gap_lines():
        """One line per gap, naming WHY it is unusable — 'missing' and 'incompatible' are
        different faults with the same remedy, and conflating them sends the reader looking
        for a package that is already installed."""
        return [*[f"  missing:      {r}" for r in report["missing"]],
                *[f"  incompatible: {req} — {why}"
                  for req, why in report["incompatible"].items()]]

    if not gaps:
        return emit(0, [f"ok: {python} imports all {len(requirements)} declared requirements "
                        f"and satisfies their capability probes"])

    if args.check:
        return emit(3, [f"{len(gaps)} of {len(requirements)} declared requirements are not usable "
                        f"from {venv}:",
                        *gap_lines(),
                        f"  fix it:  {cmd}"])

    print(f"installing {len(gaps)} requirement(s) into {venv} (missing or incompatible):")
    for r in gaps:
        print(f"  + {r}")
    install = subprocess.run(_installer(python, gaps), capture_output=True,
                             text=True, env=target_env())
    if install.returncode != 0:
        tail = (install.stderr or install.stdout or "").strip().splitlines()[-3:]
        return emit(1, ["the installer failed:", *[f"  {t}" for t in tail],
                        "  a host without network access must be repaired manually",
                        f"  retry:   {cmd}"])

    report["repaired"] = True
    state = venv_state(python, requirements)
    report["missing"] = [r for r, ok in state.items() if not ok]
    report["present"] = [r for r, ok in state.items() if ok]
    report["incompatible"] = {}
    for req in report["present"]:
        why = capability_gap(python, req)
        if why:
            report["incompatible"][req] = why
    if report["missing"] or report["incompatible"]:
        still = report["missing"] + list(report["incompatible"])
        return emit(1, [f"still cannot use after installing: {', '.join(still)}",
                        *gap_lines(),
                        *(_import_diagnosis(python, report["missing"])
                          if report["missing"] else []),
                        f"  retry:   {cmd}"])
    return emit(0, [f"repaired: {python} imports all {len(requirements)} declared requirements "
                    f"and satisfies their capability probes"])


if __name__ == "__main__":
    sys.exit(main())
