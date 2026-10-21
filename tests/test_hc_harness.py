#!/usr/bin/env python3
"""Tests for `hc harness` — the CLI driver over the harness registry.

The registry (ops/install/harnesses/registry.yaml) already declares every
coding-agent harness and its access layer. These tests pin the thing that was
missing: a single command a developer runs so wiring Pi (or any other harness)
never depends on remembering a cp + a hand-typed --tools list.

The drift this test suite exists to prevent:
  * a run line whose tool list was hand-typed and therefore rots when the
    contract grows a tool (the `--tools read,bash,edit,write,mem_context,...`
    literal in the registry is exactly that liability);
  * an MCP-layer install step that edits ANOTHER tool's config file;
  * an unknown harness name that silently does nothing.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS_CMD = REPO / "ops/scripts/hc/harness.py"
HC_PY = REPO / "ops/scripts/hc/hc.py"
TOOLS_PY = REPO / "ops/services/mycortex-mem/context_tools.py"


def _harness_module():
    """The CLI's own module — the derivation is unit-testable without spawning it."""
    spec = importlib.util.spec_from_file_location("hc_harness_mod", HARNESS_CMD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _contract_tool_names() -> set[str]:
    spec = importlib.util.spec_from_file_location("ctx_tools_for_hc_test", TOOLS_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {t["name"] for t in mod.TOOLS}


def run(*args: str, cwd: Path | None = None, env: dict | None = None):
    return subprocess.run([sys.executable, str(HARNESS_CMD), *args],
                          capture_output=True, text=True, timeout=90,
                          cwd=str(cwd) if cwd else None,
                          env={**os.environ, **env} if env else None)


def test_lists_registry_harnesses():
    r = run("list")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "pi" in out and "claude-code" in out and "codex" in out
    assert "cli-extension" in out and "mcp" in out


def test_install_pi_copies_the_extension_into_the_project(tmp_path):
    r = run("install", "pi", "--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "extensions" / "cortex-context.ts").is_file()


def _extension_registered() -> set[str]:
    """Tools the Pi extension actually registers (same parse the drift guard uses)."""
    import re
    src = (REPO / "ops/install/harnesses/pi/extensions/cortex-context.ts").read_text()
    return set(re.findall(r'tool\(\s*"([a-z_]+)"', src))


def _run_line(stdout: str) -> str:
    line = next((ln for ln in stdout.splitlines() if ln.strip().startswith("pi -e")), None)
    assert line, f"no run line in output:\n{stdout}"
    return line


def test_install_pi_prints_a_run_line_without_an_allowlist(tmp_path):
    """Pi reads the memory/session contract over MCP, so its run line carries no
    `--tools` allowlist: the surface cannot be silently narrowed by a list that ages."""
    r = run("install", "pi", "--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    line = _run_line(r.stdout)
    assert "--tools" not in line, f"Pi run line still carries an allowlist: {line}"
    assert "over MCP" in r.stdout, "the install output must name where the tools come from"


def test_the_gate_tools_are_reachable_from_a_pi_session(tmp_path):
    """Regression pin for the drift this command removes, both halves.

    The hand-typed literal in the old registry omitted `session_tool_event` and
    `session_loaded_skill` — the two tools the global pre-commit reflexion gate reads
    for a Pi session — so a developer following it got commits REFUSED, invisible
    until the commit failed. Two assertions now, because either alone can pass while
    the gate is unreachable:

    1. the run line carries NO `--tools` allowlist (nothing can be excluded), and
    2. the tools the gate reads are actually SERVED by the MCP surface Pi is pointed
       at — a regression that dropped them from the contract while still printing
       "over MCP" fails here.
    """
    out = run("install", "pi", "--dir", str(tmp_path)).stdout
    line = _run_line(out)
    assert "--tools" not in line, f"an allowlist could exclude a gate tool: {line}"
    assert "over MCP" in out, "the install output must name where the surface comes from"

    contract = _contract_tool_names()
    for gate_tool in ("session_tool_event", "session_loaded_skill"):
        assert gate_tool in contract, (
            f"{gate_tool} is not in the MCP contract — the reflexion gate cannot read "
            "a Pi session's evidence")
    # Parse the Pi ENTRY (not a substring of the whole file): the entry must be on the
    # MCP layer and the registry's MCP server must be the one that serves the contract.
    import yaml
    reg = yaml.safe_load(
        (REPO / "ops/install/harnesses/registry.yaml").read_text(encoding="utf-8"))
    pi = next(h for h in reg["harnesses"] if h["name"] == "pi")
    assert pi["layer"] == "mcp", f"pi moved off the MCP layer without moving this test: {pi['layer']}"
    server = reg.get("defaults", {}).get("mcp_server", "")
    assert "cortex-context-mcp.py" in server, (
        f"the registry's MCP server must serve the gate tools; got {server!r}")


def test_run_line_is_derived_not_the_hand_written_registry_literal(tmp_path, monkeypatch):
    """`--tools` = base + (contract ∩ artifact registrations), computed — not typed.

    No harness declares `cli-extension` today (Pi moved to MCP), so the derivation is
    driven on a synthetic entry: an artifact registering a SUBSET must yield exactly
    base + that subset and return the REST of the contract as the unexposed gap — the
    return value that makes a missing gate tool visible instead of silent.
    """
    mod = _harness_module()
    contract = mod.contract_tool_names()
    assert contract, "contract tools unavailable — fix the probe, not the test"
    subset = contract[:2]

    regdir = tmp_path / "harnesses"
    (regdir / "fake").mkdir(parents=True)
    shim = regdir / "fake" / "shim.ts"
    shim.write_text("\n".join(f'tool("{n}", {{}});' for n in subset) + "\n", encoding="utf-8")
    monkeypatch.setattr(mod, "registry_dir", lambda: regdir)
    entry = {"name": "fake", "layer": "cli-extension", "artifact": "shim.ts",
             "tools_base": ["read", "bash", "edit", "write"]}

    run_line, unexposed = mod.derived_run_line(entry)
    printed = set(run_line.split("--tools", 1)[1].strip().split(","))
    assert printed == set(subset) | {"read", "bash", "edit", "write"}
    assert unexposed == [n for n in contract if n not in subset]

    # An artifact registering NOTHING is unverifiable: expose the base only and report
    # the whole contract as the gap — never silently list tools that may not exist.
    shim.write_text("// no tool() registrations\n", encoding="utf-8")
    run_line2, gap = mod.derived_run_line(entry)
    assert run_line2.endswith("--tools read,bash,edit,write")
    assert gap == contract


def test_unknown_harness_fails_loudly():
    r = run("install", "not-a-real-harness")
    assert r.returncode != 0
    assert "unknown harness" in (r.stdout + r.stderr).lower()


def test_mcp_layer_install_prints_the_registration_and_writes_nothing(tmp_path):
    """An MCP harness's config belongs to that harness — never edit it for them."""
    r = run("install", "claude-code", "--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "mcpServers" in r.stdout
    assert not list(tmp_path.iterdir()), "install must not create files for an MCP harness"


def test_verify_reports_the_registry_and_the_store():
    r = run("verify", "pi")
    assert "registry" in r.stdout.lower()
    assert "store" in r.stdout.lower()
    # …and a return code, which this test did not assert while `verify pi` was
    # crashing with a TypeError on the one harness that declares TWO artifacts:
    # the two printed lines arrive BEFORE the crash, so a content-only assertion
    # stayed green over it.
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]


def test_verify_named_harness_reports_each_declared_artifact():
    """pi declares a LIST of artifacts; `verify pi` must judge every one of them.

    `registry_dir() / name / h["artifact"]` works only while every harness declares
    a single string, so the one that declares two raised
    `TypeError: unsupported operand type(s) for /: 'PosixPath' and 'list'` and
    exited 1 — after printing the registry and store lines that made it look fine.
    """
    r = run("verify", "pi")
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
    assert "cortex-context.ts" in r.stdout, r.stdout
    assert "cortex-governance.ts" in r.stdout, r.stdout


def _registry_fixture(tmp_path: Path, *, drop: str | None = None) -> Path:
    """A registry dir with the REAL registry, a generator stub and pi's artifacts.

    CORTEX_HARNESS_DIR is honoured by harness.py's registry_dir(), so the subject is
    pointed at this fixture instead of the checkout — the store/registry halves still
    take their real path, which is what makes the run meaningful.
    """
    regdir = tmp_path / "harnesses"
    (regdir / "pi" / "extensions").mkdir(parents=True)
    shutil.copy2(REPO / "ops/install/harnesses/registry.yaml", regdir / "registry.yaml")
    gen = regdir / "generate-harnesses.py"
    gen.write_text("import sys\nprint('generate-harnesses: OK — fixture')\n")
    for name in ("cortex-context.ts", "cortex-governance.ts"):
        if name == drop:
            continue
        (regdir / "pi" / "extensions" / name).write_text("// ext\n")
    return regdir


def test_verify_without_a_name_does_not_pass_without_checking_artifacts(tmp_path):
    """A bare PASS that judged no artifact is a false green.

    `verify` with no name checked the registry and the store and then printed
    "result: PASS" — it never looked at a single declared artifact, so a host whose
    harness files were gone reported PASS. Both directions are pinned here: with
    every declared artifact present it passes AND names them, and with one missing
    it fails.
    """
    regdir = _registry_fixture(tmp_path)
    r = run("verify", env={"CORTEX_HARNESS_DIR": str(regdir)})
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
    assert "artifact" in r.stdout.lower(), f"no artifact was judged:\n{r.stdout}"

    regdir2 = _registry_fixture(tmp_path / "second", drop="cortex-governance.ts")
    r2 = run("verify", env={"CORTEX_HARNESS_DIR": str(regdir2)})
    assert r2.returncode != 0, f"a missing declared artifact reported PASS:\n{r2.stdout}"
    assert "cortex-governance.ts" in r2.stdout, r2.stdout


def _yaml_less_runner(tmp_path: Path) -> Path:
    """Drive a target script in a process where `import yaml` FAILS.

    Reproduces the live host exactly: the tool runs under an interpreter that cannot
    import PyYAML while a capable one exists elsewhere on the same host. A poisoned
    sys.modules entry raises ImportError deterministically — no dependence on which
    python3 happens to be on PATH.
    """
    p = tmp_path / "yaml_less_runner.py"
    p.write_text("import sys, runpy\n"
                 "sys.modules['yaml'] = None\n"
                 "target, *rest = sys.argv[1:]\n"
                 "sys.argv = [target, *rest]\n"
                 "runpy.run_path(target, run_name='__main__')\n")
    return p


def test_the_cli_does_not_need_the_invoking_interpreter_to_have_yaml(tmp_path):
    """`hc harness` must resolve a CAPABLE interpreter itself.

    Measured on this host: `python3 ops/scripts/hc/harness.py list` printed
    "hc harness: PyYAML required (pip install pyyaml)" and exited 1, because
    hc.py loaded harness.py IN-PROCESS and harness.py exits at import without yaml
    — while the fleet resolver on the same host selects an interpreter that HAS it.
    """
    assert (REPO / "ops/scripts/lib/python-with-module.sh").is_file(), \
        "the fleet capability resolver is the seam this test drives"
    runner = _yaml_less_runner(tmp_path)
    r = subprocess.run([sys.executable, str(runner), str(HC_PY), "harness", "list"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
    assert "pi" in r.stdout, r.stdout


def test_the_cli_reports_could_not_verify_when_no_interpreter_can_import_yaml(tmp_path):
    """No capable interpreter anywhere is a THIRD outcome: exit 3, not a failure.

    The resolver defines 3 = COULD NOT VERIFY so callers never read "cannot check"
    as a negative result. A bare ImportError exit 1 (or a traceback) would report
    the harnesses as broken on a host that simply cannot run the check.
    """
    # The resolver's candidates include ABSOLUTE paths under HOME, so a host that HAS a
    # capable interpreter cannot be simulated by PATH alone: HOME is redirected too, and
    # PATH keeps only a `bash` link so the CLI can still shell out while `command -v
    # python3` finds nothing.
    binonly = tmp_path / "bin"
    binonly.mkdir(parents=True, exist_ok=True)
    os.symlink(shutil.which("bash") or "/bin/bash", binonly / "bash")
    (tmp_path / "home").mkdir(exist_ok=True)
    runner = _yaml_less_runner(tmp_path)
    env = {"CORTEX_HARNESS_DIR": str(_registry_fixture(tmp_path)),
           "PYTHON": "/nonexistent/python3",
           "HERMES_VENV": "/nonexistent/hermes",
           "HOME": str(tmp_path / "home"),
           # The CLI resolves agent identity from the host's env files, which the
           # redirected HOME no longer provides: without this the CLI exits 2 for a
           # missing identity and the assertion below would measure THAT, not the
           # capability path (a probe that never reached its subject).
           "HC_AGENT": "the-agent",
           "AGENT_NAME": "the-agent",
           "PATH": str(binonly)}
    r = subprocess.run([sys.executable, str(runner), str(HC_PY), "harness", "list"],
                       capture_output=True, text=True, timeout=120, env={**os.environ, **env})
    combined = (r.stdout + r.stderr).lower()
    assert r.returncode == 3, f"expected 3 (could not verify), got {r.returncode}:\n{combined[-600:]}"
    assert "could not verify" in combined or "no interpreter" in combined, combined[-600:]


def test_hc_entrypoint_dispatches_harness():
    """`hc harness` must work through the real CLI entrypoint, not just the module."""
    r = subprocess.run([sys.executable, str(REPO / "ops/scripts/hc/hc.py"), "harness", "list"],
                       capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stderr
    assert "pi" in r.stdout and "cli-extension" in r.stdout
