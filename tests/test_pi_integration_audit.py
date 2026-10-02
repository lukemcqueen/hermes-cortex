#!/usr/bin/env python3
"""The Pi integration audit must judge real hosts correctly — proven, not asserted.

The adversarial review of cycle 10477 asked for exactly this: my note claimed the audit
verifies things (a live tool-count pointer, runnable commands, AGENT_NAME on each entry)
without committed evidence that it does. Rather than argue, this drives the real script
against synthetic hosts, one thing broken at a time, and asserts BOTH directions:

  A. a complete, healthy host                      -> exit 0, every layer PASS
  B. no mcp.json on an MCP-capable Pi              -> exit 1, says run install-pi-mcp.sh
  C. an entry carrying ANOTHER agent's AGENT_NAME  -> exit 1, names it
  D. a curated skill link missing                  -> exit 1
  E. no Pi at all                                  -> exit 1 + the install command

The audit is version-aware on purpose: the MCP route needs an MCP-capable Pi, the hooks
route (git hooks + loop-gov.py) serves Pi builds without an MCP client, and reporting the
wrong route's requirements as FAIL is how an agent ends up chasing an impossible PASS.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "ops" / "scripts" / "manage" / "audit-pi-integration.sh"
CURATED = ["task-start", "agent-flow", "reflexion-check", "change-checklist",
           "survey-before-action", "agent-contract", "test-driven-development"]
_F: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        _F.append(name)


def _host(home: Path, *, mcp_json: bool = True, agent_name: str = "testagent",
          drop_link: str | None = None, pi: bool = True) -> Path:
    """Build a synthetic host. CORTEX_DEPLOY_HOME == home/.hermes-cortex."""
    dep = home / ".hermes-cortex"
    agent = home / ".pi" / "agent"
    (agent / "install" / "releases" / "1.0.0").mkdir(parents=True)
    (agent / "install" / "current-version").write_text("1.0.0\n")
    (dep / "scripts").mkdir(parents=True)
    (dep / "tools" / "loop-governance").mkdir(parents=True)
    (dep / "tools" / "loop-governance" / "loop-gov-mcp.py").write_text("# gate\n")
    (dep / "harnesses" / "pi" / "extensions").mkdir(parents=True)
    (dep / "harnesses" / "pi" / "extensions" / "cortex-context.ts").write_text("// ext\n")
    (dep / "agent.env").write_text(f"AGENT_NAME={agent_name}\n")

    if pi:
        launcher = agent / "bin" / "pi"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        # Prints 'mcp' in --help so the audit detects MCP capability the way the registry
        # says to (from the CLI's own help, never from `pi mcp list`).
        launcher.write_text("#!/bin/sh\ncase \"$1\" in --help) echo 'tools: read bash edit write; '\n"
                            "echo 'commands: install remove list config auth mcp';; "
                            "--version) echo 1.0.0;; esac\n")
        launcher.chmod(0o755)

    (agent / "settings.json").write_text('{"extensions": ["' + str(dep / "harnesses" / "pi"
                                       / "extensions" / "cortex-context.ts") + '"], "skills": ["'
                                       + str(agent / "cortex-skills") + '"]}\n')
    (agent / "cortex-skills").mkdir(exist_ok=True)
    for s in CURATED:
        if s == drop_link:
            continue
        (agent / "cortex-skills" / s).write_text("# skill\n")

    (dep / "skills.yaml").write_text("version: 1\nalways:\n"
                                     + "".join(f"  - name: {s}\n" for s in CURATED))

    for name, script in (("loop-governance", dep / "tools" / "loop-governance" / "loop-gov-mcp.py"),
                         ("tasks", dep / "scripts" / "task-mcp.py"),
                         ("executor", dep / "scripts" / "executor-mcp.py"),
                         ("agent-bus", dep / "scripts" / "cortex-bus-mcp.py")):
        script.write_text("# mcp server\n")
    if mcp_json:
        import json
        entries = {}
        for name, script in (("loop-governance", dep / "tools" / "loop-governance" / "loop-gov-mcp.py"),
                             ("tasks", dep / "scripts" / "task-mcp.py"),
                             ("executor", dep / "scripts" / "executor-mcp.py"),
                             ("agent-bus", dep / "scripts" / "cortex-bus-mcp.py")):
            # one entry intentionally carries a foreign identity in the C case
            who = "someone-else" if (agent_name != "testagent" and name == "agent-bus") else agent_name
            entries[name] = {"command": sys.executable, "args": [str(script)],
                             "env": {"AGENT_NAME": who}}
        (agent / "mcp.json").write_text(json.dumps({"mcpServers": entries}))
    return dep


def _path_without_pi() -> str:
    """A PATH with no `pi` executable on it.

    The audit detects Pi via `$HOME/.pi/agent/bin/pi`, then falls back to
    `command -v pi` on PATH. Leaving PATH inherited makes the synthetic host
    NOT the only source of truth: anything that happens to put a `pi` on the
    runner's PATH (a real install, a leaked temp bin dir) makes the
    "no Pi at all" case pass the audit and fail the test — intermittently,
    depending only on the environment. The cases below are about the synthetic
    host, so PATH is scrubbed for all of them.
    """
    keep = []
    for d in os.environ.get("PATH", "/usr/bin:/bin").split(os.pathsep):
        if d and not os.path.exists(os.path.join(d, "pi")):
            keep.append(d)
    return os.pathsep.join(keep) or "/usr/bin:/bin"


def _run(home: Path, dep: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(AUDIT)], capture_output=True, text=True,
                          env={**os.environ, "HOME": str(home),
                               "CORTEX_DEPLOY_HOME": str(dep), "PATH": _path_without_pi()})


def test_the_cases_are_immune_to_a_pi_on_the_inherited_path() -> None:
    """Control: a `pi` on PATH must NOT leak into the 'no Pi at all' case.

    This is the exact mechanism of the intermittent failure observed in
    full-suite runs (2026-10-02): the audit's fallback is `command -v pi`, so an
    inherited PATH carrying a `pi` made case E report RESULT: PASS.
    """
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        binp = td / "fakebin"
        binp.mkdir()
        fake = binp / "pi"
        fake.write_text("#!/bin/sh\ncase \"$1\" in --help) echo 'commands: install remove mcp';;"
                        " --version) echo 9.9.9;; esac\n")
        fake.chmod(0o755)

        home = td / "home"
        dep = _host(home, pi=False)

        original = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{binp}{os.pathsep}{original}"
        try:
            r = _run(home, dep)
        finally:
            os.environ["PATH"] = original

        assert r.returncode == 1, (
            "a `pi` on the inherited PATH satisfied the audit for a host with no Pi — "
            f"the synthetic host must be the only source of truth. stdout tail:\n{r.stdout[-400:]}")


def test_pi_integration_audit() -> None:
    print("A. a complete host passes")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        dep = _host(home)
        r = _run(home, dep)
        _check("exit 0", r.returncode == 0, r.stdout[-400:])
        _check("reports RESULT: PASS", "RESULT: PASS" in r.stdout, r.stdout[-200:])

    print("B. missing mcp.json on an MCP-capable Pi fails, with the fix")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        dep = _host(home, mcp_json=False)
        r = _run(home, dep)
        _check("exit 1", r.returncode == 1)
        _check("names install-pi-mcp.sh", "install-pi-mcp.sh" in r.stdout, r.stdout[-200:])

    print("C. an entry with a foreign AGENT_NAME fails")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        dep = _host(home, agent_name="other-agent")
        r = _run(home, dep)
        _check("exit 1", r.returncode == 1, r.stdout[-300:])
        _check("names the offending entry", "agent-bus" in r.stdout and "AGENT_NAME" in r.stdout,
               r.stdout[-300:])

    print("D. a missing curated skill link fails")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        dep = _host(home, drop_link="reflexion-check")
        r = _run(home, dep)
        _check("exit 1", r.returncode == 1)
        _check("names the missing link", "reflexion-check" in r.stdout, r.stdout[-300:])

    print("E. no Pi at all fails, with the install command")
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        dep = _host(home, pi=False)
        r = _run(home, dep)
        # Detail must name the ROUTE the audit took, not just the exit code: an
        # inherited `pi` on PATH satisfies this case for a host that has none, and
        # that is invisible in a bare "expected 1" message (2026-10-02).
        why = f"pi_on_PATH={shutil.which('pi')!r} home_pi={(home / '.pi' / 'agent' / 'bin' / 'pi').exists()}"
        _check("exit 1", r.returncode == 1, why + " | " + r.stdout[-200:])
        _check("reports Pi missing", "not installed" in r.stdout or "FAIL" in r.stdout, why)
        _check("gives the install command", "npm install -g @earendil-works/pi-coding-agent" in r.stdout,
               why + " | " + r.stdout[-300:])

    assert not _F, f"{len(_F)} audit check(s) failed: {', '.join(_F)}"


if __name__ == "__main__":
    test_pi_integration_audit()
    print("\n✅ Pi integration audit checks passed")
    sys.exit(0)
