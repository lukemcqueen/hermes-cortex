#!/usr/bin/env python3
"""The Pi audit must judge a host-local FOREIGN mcp.json entry correctly.

WHY THIS IS ITS OWN FILE: `tests/test_pi_integration_audit.py` was left with an
earlier session's work STAGED but uncommitted in this tree (2026-10-12, same agent —
`git status` shows staged vs unstaged, never WHO staged it, so this was first
mis-read as another session's). Adding cases there would fold that stranded work into
this change; the cases live here until that work is landed on its own.

  G.  a host with a hand-registered foreign server (deepseek)   -> exit 0, PASS,
      the foreign entry REPORTED as outside the audit
  G2. that foreign entry pointing at a missing script           -> exit 1, named

The audit's `AGENT_NAME` rule is a CORTEX identity contract: every cortex entry must
carry THIS host's agent name, because a copied-in mcp.json otherwise hands the agent
another host's bus identity. It was applied to EVERY entry, so a host-local add-on
with no env at all (measured: the DeepSeek adversarial-review server) made a healthy
host report FAIL. Scoping the rule must not make the audit blind — hence G2, which
keeps the command/script check on foreign entries.

Run:  python3 tests/test_pi_integration_foreign_server.py    (also collected by pytest)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Overridable so the SAME cases can be run against a pre-change copy of the audit
# (the discrimination proof: they must FAIL there, or they test nothing).
AUDIT = Path(os.environ.get("PI_AUDIT_SCRIPT")
             or REPO / "ops" / "scripts" / "manage" / "audit-pi-integration.sh")
CURATED = ["task-start", "agent-flow", "reflexion-check", "change-checklist",
           "survey-before-action", "agent-contract", "test-driven-development"]
_F: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        _F.append(name)


def _path_without_pi() -> str:
    """A PATH with no `pi` on it: the synthetic host must be the only source of truth."""
    keep = [d for d in os.environ.get("PATH", "/usr/bin:/bin").split(os.pathsep)
            if d and not os.path.exists(os.path.join(d, "pi"))]
    return os.pathsep.join(keep) or "/usr/bin:/bin"


def _host(home: Path, *, foreign_script_missing: bool = False) -> Path:
    """A healthy Pi host (five cortex servers, correct identity) plus ONE foreign entry."""
    dep = home / ".hermes-cortex"
    agent = home / ".pi" / "agent"
    (agent / "install" / "1.0.0-parent").mkdir(parents=True, exist_ok=True)
    (agent / "install" / "current-version").write_text("1.0.0\n")
    (dep / "tools" / "loop-governance").mkdir(parents=True, exist_ok=True)
    (dep / "scripts").mkdir(parents=True, exist_ok=True)
    (dep / "harnesses" / "pi" / "extensions").mkdir(parents=True, exist_ok=True)
    (dep / "harnesses" / "pi" / "extensions" / "cortex-context.ts").write_text("// ext\n")
    (dep / "tools" / "loop-governance" / "loop-gov-mcp.py").write_text("# gate\n")
    (dep / "agent.env").write_text("AGENT_NAME=testagent\n")

    launcher = agent / "bin" / "pi"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("#!/bin/sh\ncase \"$1\" in --help) echo 'tools: read bash; '; "
                        "echo 'commands: install remove list config auth mcp';; "
                        "--version) echo 1.0.0;; esac\n")
    launcher.chmod(0o755)
    (agent / "settings.json").write_text(json.dumps({
        "extensions": [str(dep / "harnesses" / "pi" / "extensions" / "cortex-context.ts")],
        "skills": [str(agent / "cortex-skills")]}))
    (agent / "cortex-skills").mkdir(exist_ok=True)
    for s in CURATED:
        (agent / "cortex-skills" / s).write_text("# skill\n")
    (dep / "skills.yaml").write_text("version: 1\nalways:\n"
                                     + "".join(f"  - name: {s}\n" for s in CURATED))

    entries = {}
    for name, script in (("loop-governance", dep / "tools" / "loop-governance" / "loop-gov-mcp.py"),
                         ("tasks", dep / "scripts" / "task-mcp.py"),
                         ("executor", dep / "scripts" / "executor-mcp.py"),
                         ("agent-bus", dep / "scripts" / "cortex-bus-mcp.py"),
                         ("cortex-context", dep / "scripts" / "cortex-context-mcp.py")):
        script.write_text("# mcp server\n")
        entries[name] = {"command": sys.executable, "args": [str(script)],
                         "env": {"AGENT_NAME": "testagent"}}

    # THE FOREIGN ENTRY: the real shape — no `env` at all, no cortex semantics.
    fscript = dep / "scripts" / "mcp_deepseek_server.py"
    if not foreign_script_missing:
        fscript.write_text("# foreign mcp server\n")
    entries["deepseek"] = {
        "command": sys.executable,
        "args": [str(fscript if not foreign_script_missing else home / "gone" / "mcp_deepseek_server.py")],
        "timeout": 300,
        "description": "DeepSeek adversarial review via OpenRouter"}

    (agent / "mcp.json").write_text(json.dumps({"mcpServers": entries}))
    return dep


def _run(home: Path, dep: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(AUDIT)], capture_output=True, text=True,
                          env={**os.environ, "HOME": str(home),
                               "CORTEX_DEPLOY_HOME": str(dep), "PATH": _path_without_pi()})


def test_a_foreign_server_is_reported_not_judged() -> None:
    print("G. a host-local FOREIGN server (deepseek) is reported, never judged")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        dep = _host(home)
        r = _run(home, dep)
        _check("exit 0", r.returncode == 0, r.stdout[-400:])
        _check("reports RESULT: PASS", "RESULT: PASS" in r.stdout, r.stdout[-200:])
        _check("names the foreign server as outside the audit",
               any("deepseek" in ln and "NOT audited" in ln for ln in r.stdout.splitlines()),
               r.stdout[-400:])
        _check("does not blame it for a missing cortex identity",
               not any("deepseek" in ln and "AGENT_NAME" in ln for ln in r.stdout.splitlines()),
               r.stdout[-400:])


def test_a_broken_foreign_entry_still_fails() -> None:
    print("G2. a foreign server whose script is missing IS still a failure")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        dep = _host(home, foreign_script_missing=True)
        r = _run(home, dep)
        _check("exit 1", r.returncode == 1, r.stdout[-300:])
        _check("names the broken entry", "deepseek" in r.stdout, r.stdout[-300:])


def test_the_installer_leaves_a_foreign_entry_alone() -> None:
    """H. The doc's claim, as a re-runnable TEST rather than a pasted transcript.

    `PI_MCP_FILE` points at a scratch config and HOME stays REAL: the installer
    resolves its interpreter from the deployed layout under $HOME, so neutering HOME
    would make it refuse for the wrong reason (a probe bug, not a finding).
    """
    print("H. install-pi-mcp.sh add + --remove keep a foreign entry")
    installer = REPO / "ops" / "scripts" / "install" / "install-pi-mcp.sh"
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {
            "deepseek": {"command": sys.executable,
                         "args": ["/tmp/mcp_deepseek_server.py"]},
            "user-owned": {"command": "/bin/true"}}}))
        env = {**os.environ, "PI_MCP_FILE": str(cfg)}
        add = subprocess.run(["bash", str(installer)], capture_output=True, text=True, env=env)
        added = sorted(json.loads(cfg.read_text())["mcpServers"])
        rm = subprocess.run(["bash", str(installer), "--remove"],
                            capture_output=True, text=True, env=env)
        remaining = sorted(json.loads(cfg.read_text())["mcpServers"])

        _check("add rc=0", add.returncode == 0, (add.stdout + add.stderr)[-300:])
        _check("add registered the five cortex servers",
               all(s in added for s in ("loop-governance", "tasks", "executor",
                                        "agent-bus", "cortex-context")), str(added))
        _check("remove rc=0", rm.returncode == 0, (rm.stdout + rm.stderr)[-300:])
        _check("the foreign entry survives --remove (and the cortex set does not)",
               remaining == ["deepseek", "user-owned"], str(remaining))


if __name__ == "__main__":
    test_a_foreign_server_is_reported_not_judged()
    test_a_broken_foreign_entry_still_fails()
    test_the_installer_leaves_a_foreign_entry_alone()
    assert not _F, f"{len(_F)} check(s) failed: {', '.join(_F)}"
    print("\n✅ foreign-server scoping checks passed")
    sys.exit(0)
