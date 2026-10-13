#!/usr/bin/env python3
"""Audit MCP server WIRING, not just presence — a registered server can still be dead.

WHY. Kustos reported "No loop-governance MCP tools in catalog" while the doctor said
`MCP server (loop-governance): PASS — configured in config.yaml`: the check tested whether the
server's NAME appeared in the config text, never whether the registered command and arguments
still exist on disk. A registration that points at a missing venv, wrapper or script loads
NOTHING and says nothing — the same false-pass shape as "the venv exists, so it must work".

Pure functions here take the config TEXT and a path-existence callable, so the parsing and the
verdicts are unit-testable without a live host. The CLI reads a real config.

USAGE
  python3 mcp-wiring.py --config ~/.hermes/config.yaml            # report
  python3 mcp-wiring.py --config ~/.hermes/config.yaml --json     # last line is JSON
  python3 mcp-wiring.py --config ... --expected loop-governance,tasks

EXIT
  0 every expected server is present AND its paths exist
  1 at least one entry is wired to something that is not there
  2 usage error
  3 COULD NOT VERIFY — no readable config / no expected servers to check
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: name -> server script (relative), and whether only an orchestrator host is expected to
#: carry it. These MUST agree with the doctor's own map (ops/scripts/manage/cortex_doctor/
#: config.py, EXPECTED_MCP_SERVERS / ORCH_ONLY_MCP_SERVERS) — a test asserts the two match, so
#: there is one source of truth even though the CLI cannot import the doctor's package.
DEFAULT_EXPECTED = {
    "agent-bus": "mcp-servers/cortex-bus-mcp.py",
    "loop-governance": "mcp-servers/loop-gov-mcp.py",
    "tasks": "mcp-servers/task-mcp.py",
    "executor": "mcp-servers/executor-mcp.py",
}
ORCH_ONLY = {"agent-bus", "executor"}

#: A command inside the HERMES venv works, but it is the tree the fleet is migrating off
#: (Luke 2026-10-13: use the cortex venv). Worth a warning, not a failure.
HERMES_VENV_MARK = "hermes-agent/venv"
CORTEX_VENV = "~/.hermes-cortex/venv/bin/python3"


def _entry_blocks(config_text):
    """{server: block} for the `mcp_servers:` mapping, by indentation (no PyYAML needed).

    The ENTRY indent is the shallowest key indent inside the block, not a fixed 2: a child key
    like `command:` sits deeper and must not start a new entry.
    """
    lines = config_text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if re.match(r"^mcp_servers:\s*$", l))
    except StopIteration:
        return {}
    body = []
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith((" ", "\t")):
            break                              # next top-level key ends mcp_servers
        body.append(line)

    key_re = re.compile(r"^(\s+)(\S+):")
    indents = []
    for line in body:
        _m = key_re.match(line)
        if _m and not line.strip().startswith("-"):
            indents.append(len(_m.group(1)))
    if not indents:
        return {}
    entry_indent = min(indents)

    blocks, current, name = {}, [], None

    def flush():
        if name:
            blocks[name] = "\n".join(current)

    for line in body:
        m = key_re.match(line)
        if m and len(m.group(1)) == entry_indent and not line.strip().startswith("-"):
            flush()
            name, current = m.group(2), [line]
            continue
        if name is not None:
            current.append(line)
    flush()
    return blocks


def _paths_of(block):
    """Every path a wiring entry needs: the command itself and each argument.

    `[ \\t]` rather than `\\s` around the values: `\\s` matches a NEWLINE, so `args:` with its
    list on the following lines would swallow the next line as the value (caught by a test —
    it produced a path of '- /path/to/server.py').
    """
    out = []
    m = re.search(r"^[ \t]*command:[ \t]*(.+?)[ \t]*$", block, re.MULTILINE)
    if m:
        out.append(m.group(1).strip().strip("'\""))
    m = re.search(r"^[ \t]*args:[ \t]*(.*?)[ \t]*$", block, re.MULTILINE)
    if m and m.group(1).strip() not in ("", "[]"):
        arg = m.group(1).strip()
        if arg.startswith("[") and arg.endswith("]"):
            out.extend(a.strip().strip("'\"") for a in arg[1:-1].split(",") if a.strip())
        else:
            out.append(arg.strip().strip("'\""))
    for line in block.splitlines():                     # YAML list form: "- /path"
        s = line.strip()
        if s.startswith("- ") and "/" in s:
            out.append(s[2:].strip().strip("'\""))
    return [p for p in out if p]


def audit(config_text, expected=None, exists=None, is_orch=True, which=None):
    """[(name, status, detail, fix)] where status is PASS / WARN / FAIL.

    `exists` and `which` are injected (defaults: Path().exists, shutil.which) so the rules are
    testable hermetically.
    """
    import shutil as _shutil
    expected = DEFAULT_EXPECTED if expected is None else expected
    exists = exists or (lambda p: Path(str(p)).expanduser().exists())
    which = which or _shutil.which
    blocks = _entry_blocks(config_text or "")
    results = []

    def _missing_paths(block):
        """Paths that are not there. A BARE command name is resolved on PATH, not as a path —
        treating it as one reported 'python3 does not exist'."""
        gone, bare = [], []
        for p in _paths_of(block):
            if p.startswith("-"):
                continue
            if "/" in p:
                if not exists(p):
                    gone.append(p)
            elif which(p):
                bare.append(p)              # resolvable, but not the fleet venv
            else:
                gone.append(p)              # not resolvable anywhere
        return gone, bare

    for name, script in expected.items():
        if name in ORCH_ONLY and not is_orch:
            if name in blocks:
                results.append((name, "WARN",
                                "configured on a non-orchestrator host",
                                f"Remove the {name} entry from mcp_servers"))
            else:
                results.append((name, "PASS", "not configured (correct here)", ""))
            continue

        block = blocks.get(name)
        if block is None:
            results.append((name, "FAIL", "not configured",
                            f"hermes mcp add {name} --command "
                            f"~/.hermes-cortex/venv/bin/python3 --args ~/hermes-cortex/{script}"))
            continue

        gone, bare = _missing_paths(block)
        if gone:
            # Present but pointing at nothing: the false-pass the name-only check gave.
            results.append((name, "FAIL",
                            "configured, but these paths do NOT exist: " + ", ".join(gone),
                            f"hermes mcp remove {name} && hermes mcp add {name} "
                            f"--command ~/.hermes-cortex/venv/bin/python3 "
                            f"--args ~/hermes-cortex/{script}"
                            "   (or run cortex-update.sh to deploy the missing pieces)"))
            continue
        cmd = re.search(r"^[ \t]*command:[ \t]*(.+?)[ \t]*$", block, re.MULTILINE)
        command = cmd.group(1).strip().strip("'\"") if cmd else ""
        if bare or HERMES_VENV_MARK in command:
            why = ("a bare command, not the fleet venv: " + ", ".join(bare)) if bare else \
                  f"the HERMES venv ({command}) — the tree the fleet is migrating off"
            results.append((name, "WARN", f"registered against {why}",
                            f"hermes mcp remove {name} && hermes mcp add {name} "
                            f"--command {CORTEX_VENV} --args ~/hermes-cortex/{script}"
                            f"   (there is no 'hermes mcp update'; re-add it)"))
            continue
        results.append((name, "PASS", "configured and its paths exist", ""))
        continue
    return results


def find_config(path=None):
    """An EXPLICIT path is used as given — never silently swapped for another file, which
    would audit a different host's wiring and report a confident wrong answer."""
    if path:
        cand = Path(path).expanduser()
        return cand if cand.is_file() else None
    for cand in ("~/.hermes/config.yaml", "~/.hermes/config.yml"):
        if Path(cand).expanduser().is_file():
            return Path(cand).expanduser()
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit MCP server wiring (paths, not just names).")
    ap.add_argument("--config", default=None, help="config file (default ~/.hermes/config.yaml)")
    ap.add_argument("--expected", default=None, help="comma-separated server names to require")
    ap.add_argument("--orch", action="store_true", help="this host is an orchestrator")
    ap.add_argument("--json", action="store_true", help="last line is machine-readable JSON")
    args = ap.parse_args(argv)

    cfg = find_config(args.config)
    if cfg is None:
        print("COULD NOT VERIFY — no readable MCP config (looked for ~/.hermes/config.yaml)",
              file=sys.stderr)
        return 3
    expected = DEFAULT_EXPECTED
    if args.expected:
        names = [n.strip() for n in args.expected.split(",") if n.strip()]
        expected = {n: DEFAULT_EXPECTED.get(n, "") for n in names}

    results = audit(cfg.read_text(errors="replace"), expected, is_orch=args.orch)
    print(f"config: {cfg}")
    for name, status, detail, fix in results:
        print(f"  {status:4} {name}: {detail}")
        if fix and status != "PASS":
            print(f"       fix: {fix}")
    bad = [r for r in results if r[1] == "FAIL"]
    if args.json:
        print(json.dumps({"config": str(cfg),
                          "entries": [{"name": n, "status": s, "detail": d} for n, s, d, _ in results],
                          "failures": [n for n, s, _, _ in results if s == "FAIL"]}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
