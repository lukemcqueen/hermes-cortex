#!/usr/bin/env python3
"""Tests for the context access layers and the harness registry (S2c).

The point of these tests is DRIFT, not happy paths. With several access layers
over one implementation the realistic failure is not "the tool is broken" — it is
"one layer quietly disagrees with another": a Pi extension registering a tool the
implementation does not have, or a registry entry whose generated docs are stale.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
TOOLS_PY = REPO / "ops/services/mycortex-mem/context_tools.py"
CLI_PY = REPO / "ops/scripts/cortex-context.py"
MCP_PY = REPO / "mcp-servers/cortex-context-mcp.py"
HARNESS_DIR = REPO / "ops/install/harnesses"
REGISTRY = HARNESS_DIR / "registry.yaml"
PI_EXT = HARNESS_DIR / "pi/extensions/cortex-context.ts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tools():
    return _load(TOOLS_PY, "context_tools_under_test")


def run_cli(*args: str, env: dict | None = None):
    return subprocess.run([sys.executable, str(CLI_PY), *args],
                          capture_output=True, text=True, timeout=90, env=env)


# ── The tool surface ─────────────────────────────────────────────

def test_both_families_are_present(tools):
    names = set(tools.HANDLERS)
    assert {n for n in names if n.startswith("mem_")} >= {
        "mem_profile", "mem_search", "mem_context", "mem_conclude"}
    assert {n for n in names if n.startswith("session_")} >= {
        "session_checkpoint", "session_restore", "session_list",
        "session_search", "session_note", "session_close"}


def test_every_tool_has_metadata_and_a_handler(tools):
    """Metadata and handlers must not drift apart: a tool described but not
    implemented fails only when an agent calls it."""
    described = {t["name"] for t in tools.TOOLS}
    assert described == set(tools.HANDLERS)


def test_mcp_schema_translation(tools):
    for t in tools.TOOLS:
        schema = tools.tool_schema_for_mcp(t)
        assert schema["type"] == "object"
        assert schema["required"] == t["required"]
        for key in t["params"]:
            assert key in schema["properties"]
            if key in t["required"]:
                assert key in schema["properties"], key


def test_dispatch_never_raises_on_unknown_tool(tools):
    assert "unknown tool" in tools.dispatch("nope", {})


def test_dispatch_reports_bad_arguments_as_a_message_not_a_crash(tools):
    assert "error:" in tools.dispatch("mem_search", {})       # query required
    assert "error:" in tools.dispatch("session_note", {})     # text required


def test_identity_precedence_args_beat_env(tools, monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_HARNESS", "from-env")
    assert tools.resolve_identity({"harness": "from-arg"})[0] == "from-arg"
    # session_key short-circuits to an exact session, never a guess
    assert tools.resolve_identity({"session_key": "k:r:b"}) == ("k:r:b", "", "")


# ── The CLI access layer ─────────────────────────────────────────

def test_cli_lists_tools():
    r = run_cli("--list")
    assert r.returncode == 0
    assert "session_checkpoint" in r.stdout and "mem_context" in r.stdout


def test_cli_tools_json_is_machine_readable():
    r = run_cli("--tools-json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert isinstance(data, list) and data
    for t in data:
        assert {"name", "description", "params", "required"} <= set(t)


def test_cli_unknown_tool_exits_nonzero():
    r = run_cli("not_a_tool")
    assert r.returncode == 1
    assert "unknown tool" in r.stderr


def test_cli_malformed_json_exits_nonzero():
    assert run_cli("mem_context", "{not json").returncode == 1
    assert run_cli("mem_context", "[1,2,3]").returncode == 1


def test_cli_reaches_the_store_and_exits_zero():
    """Real store, real call — the point is that a HARNESS can rely on exit 0."""
    r = run_cli("mem_context", "{}",
                env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()),
                     "CORTEX_SESSION_HARNESS": "pytest"})
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert "card" in payload and "session_key" in payload


# ── Drift guards ─────────────────────────────────────────────────

def test_pi_extension_registers_NO_tools(tools):
    """ONE way in per capability: the tools come from the shared MCP server.

    They used to be registered here by hand, which made TWO definitions of the
    same tools — and the hand-written one broke SILENTLY when Pi moved
    0.87.1 → 1.0.0 ("definition.execute is not a function") while the store was
    healthy. Registering them here again reintroduces exactly that phantom.
    """
    src = PI_EXT.read_text()
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith(("*", "//", "/*")))
    assert "registerTool" not in code, (
        "the extension must NOT register tools — they arrive from the cortex-context "
        "MCP server, so a second definition here is the duplicate surface")
    assert "pi.on(" in code, "the lifecycle hooks must stay — that is the whole point"


def test_pi_extension_uses_the_shared_cli_not_its_own_logic():
    src = PI_EXT.read_text()
    assert "cortex-context.py" in src, "extension must call the shared CLI"
    # A second implementation of the semantics is the defect this guards against.
    assert "psql" not in src and "mycortex_mem" not in src


def test_pi_extension_wires_the_lifecycle_trigger():
    """The trigger half must live in the harness hooks, never in a prompt."""
    src = PI_EXT.read_text()
    assert "turn_end" in src, "no turn_end hook — nothing writes checkpoints"
    assert "before_agent_start" in src, "no restore hook — sessions cannot resume"


def test_pi_extension_uses_the_REAL_event_api():
    """Regression guard. Both of these were wrong once and failed SILENTLY:

      * the handler's first parameter is the EVENT, not a ctx — reading
        `ctx.completed?.()` yielded undefined and wrote EMPTY checkpoints;
      * before_agent_start injection is the RETURN value — there is no
        ctx.addSystemPrompt(), and calling one did nothing.

    A checkpoint that looks like continuity and carries none is worse than none,
    so assert the shape rather than trusting a stderr marker.
    """
    src = PI_EXT.read_text()
    # Compare CODE, not prose: the docstring legitimately NAMES the method it
    # says does not exist. Asserting against the raw text was a bad probe — it
    # flagged its own explanation.
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith(("*", "//", "/*")))
    assert "addSystemPrompt(" not in code, "no such ctx method — injection is the return value"
    assert "ctx.completed" not in code and "ctx.pending" not in code, \
        "those live on the event, not the ctx"
    assert re.search(r'pi\.on\(\s*"turn_end"\s*,\s*async\s*\(\s*event', code), \
        "turn_end handler must take (event, ctx)"
    assert "systemPrompt:" in code, "before_agent_start must RETURN the injected prompt"
    # Empty states must be SILENT on stderr (no cluttering a TUI prompt).
    # The runbook still verifies "no empty checkpoint" through the executed
    # guard, not through a stderr marker.
    assert "CORTEX_CHECKPOINT_EMPTY" not in code, \
        "empty-turn noise on stderr is gone — stay silent unless genuinely broken"


def test_pi_extension_stderr_is_failure_only():
    """Diagnostics that are not failures must NOT write to stderr: they surface
    directly above the Pi TUI input prompt and drown out the real signal.

    Keep exactly the failure writes — a CLI crash (CORTEX_FAIL) and a tool-event
    write that fell over (CORTEX_TOOL_EVENT … FAILED). Everything else returns
    silently, and a resume marker is not a failure.
    """
    src = PI_EXT.read_text()
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith(("*", "//", "/*")))
    # Reads the code's write calls — status quotes are prose, not the call.
    writes = [ln.strip() for ln in code.splitlines()
              if "process.stderr.write(" in ln]
    assert "CORTEX_FAIL" in src, "a real CLI error must still be reported"
    for marker in ("CORTEX_RESUME", "CORTEX_CHECKPOINT_EMPTY"):
        assert marker not in code, f"{marker} is not a failure — remove the stderr write"
    assert "recorded" not in writes, "the success path must not announce itself"


def test_pi_context_tools_are_registered_as_the_shared_MCP_server():
    """The tool surface is a CONFIG entry pointing at the SHARED server.

    Not a shim, and not a Pi-specific implementation: the same
    cortex-context-mcp.py Claude Code and Codex use, whose schemas are derived
    from the contract. The registry and the installer must agree, or a host
    follows one and silently lacks the other.
    """
    installer = (REPO / "ops/scripts/install/install-pi-mcp.sh").read_text()
    assert "cortex-context" in installer, "pi must register the cortex-context MCP server"
    assert "cortex-context-mcp.py" in installer, "…and it must be the deployed shared server"
    # The registered server must be the contract-derived one, not a reimplementation.
    mcp_src = MCP_PY.read_text()
    assert "context_tools.py" in mcp_src
    assert "def mem_context" not in mcp_src and "def session_checkpoint" not in mcp_src
    # Registry must not drift from the installer.
    reg = yaml.safe_load(REGISTRY.read_text())
    pi = next(h for h in reg["harnesses"] if h["name"] == "pi")
    assert pi["layer"] == "mcp", "pi reads its context tools over MCP now"
    ctx = pi["capabilities"]["context"]
    assert ctx["adapter"] == "mcp"
    assert "install-pi-mcp.sh" in ctx["register"]


def test_pi_extension_EXECUTES():
    """EXECUTE the extension — a static guard cannot see behaviour.

    Runs `ops/install/harnesses/pi/verify-extension.mjs`, which loads the REAL
    extension through pi's own jiti loader, hands it a stub `pi`, then DRIVES the
    lifecycle hooks against a throwaway CLI (the store is never touched): it
    asserts the extension registers ZERO tools (they come from the shared MCP
    server) and that `before_agent_start` injects the restored checkpoint and
    `turn_end` writes one — including NOT writing a silently-empty one.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available — cannot execute the extension")
    r = subprocess.run([node, str(HARNESS_DIR / "pi" / "verify-extension.mjs")],
                       capture_output=True, text=True, timeout=180)
    # A mise/binary pi install has no node_modules/jiti for the guard to drive a
    # .ts extension with; the guard exits 0 with "EXTENSION SKIPPED" in that case.
    # That is an environment skip, not a broken wiring — a host with the
    # npm-managed layout (where jiti resolves) exercises the real guard.
    if "EXTENSION SKIPPED" in r.stdout:
        pytest.skip("verify-extension.mjs cannot locate a jiti loader on this pi install — run on an npm-managed pi host")
    assert r.returncode == 0, f"extension tool wiring is broken:\n{r.stdout}\n{r.stderr}"
    assert "EXTENSION OK" in r.stdout


def _run_pi_guard(node: str, workdir: Path, extra_env: dict | None = None):
    """Run the pi extension guard from `workdir`; return (rc, stdout, stderr)."""
    env = dict(os.environ)
    env.setdefault("CORTEX_STUB_FAIL", "0")
    env.update(extra_env or {})
    return subprocess.run([node, str(workdir / "verify-extension.mjs")],
                          capture_output=True, text=True, timeout=180, cwd=str(workdir), env=env)


def _routine_stderr_lines(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines() if line.startswith("CORTEX_")]


def _leaky_variant(tmp_path: Path) -> Path:
    """The guard's own RED case: a copy of the extension that DOES pollute the TUI.

    `execFile` pipes the child's stdio, so the realistic regression is not an inherited
    fd — it is an edit that "helpfully" echoes the captured child stderr onto the
    harness's stderr. That is the shape this test must catch, so the variant is built
    from source rather than asserted.
    """
    workdir = tmp_path / "pi-leak"
    (workdir / "extensions").mkdir(parents=True)
    shutil.copy(HARNESS_DIR / "pi" / "verify-extension.mjs", workdir / "verify-extension.mjs")
    source = PI_EXT.read_text()
    capture = "    const { stdout } = await run("
    ret = "    return stdout.trim();\n"
    assert capture in source and ret in source, "the guard's injection anchors moved — update this RED case"
    leaky = source.replace(capture, "    const { stdout, stderr } = await run(", 1)
    leaky = leaky.replace(ret, "    if (stderr) process.stderr.write(String(stderr));\n" + ret, 1)
    (workdir / "extensions" / "cortex-context.ts").write_text(leaky)
    return workdir


def test_pi_extension_keeps_routine_output_off_the_prompt_area(tmp_path):
    """In Pi, the harness's stderr IS the prompt area.

    Three things must hold at the FD level (measured in the parent, because patching
    `process.stderr.write` inside the guard cannot see a write that bypasses it):

      1. a child's stderr never reaches it (execFile pipes the child's stdio);
      2. NOTHING routine is written there on the success path — no CORTEX_RESUME /
         CORTEX_CHECKPOINT_EMPTY scribbling over what the user is typing;
      3. genuine failures are still LOUD — a silent memory failure reads as "the agent
         had no memory", a different and wrong conclusion.

    The routine trace stays reachable via CORTEX_CONTEXT_DEBUG=1 (asserted), so this
    gates diagnostics, it does not delete them.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available — cannot execute the extension")

    healthy = _run_pi_guard(node, HARNESS_DIR / "pi")
    assert healthy.returncode == 0, f"the guard failed:\n{healthy.stdout}\n{healthy.stderr}"
    assert "MARKER-CHILD-NOISE" not in healthy.stderr, (
        "a child's stderr reached the harness's stderr (the Pi prompt area):\n" + healthy.stderr)
    assert not _routine_stderr_lines(healthy.stderr), (
        "routine output reached the Pi prompt area:\n" + healthy.stderr)

    debug = _run_pi_guard(node, HARNESS_DIR / "pi", {"CORTEX_CONTEXT_DEBUG": "1"})
    assert _routine_stderr_lines(debug.stderr), (
        "CORTEX_CONTEXT_DEBUG=1 no longer surfaces the routine trace — the diagnostics "
        "were deleted rather than gated")

    failing = _run_pi_guard(node, HARNESS_DIR / "pi", {"CORTEX_STUB_FAIL": "1"})
    assert "CORTEX_FAIL" in failing.stderr, (
        "a failing CLI no longer reports itself — a silent failure is indistinguishable "
        "from an agent with no memory")

    # Non-vacuity: the same guard, pointed at an extension that echoes the child's
    # captured stderr, must see the leak.
    leaky = _run_pi_guard(node, _leaky_variant(tmp_path))
    assert "MARKER-CHILD-NOISE" in leaky.stderr, (
        "the child-stderr check cannot fail — an extension that echoes captured child "
        "stderr leaked nothing to the parent's stderr, so the check is vacuous")


def test_pi_extension_traces_routine_output_to_a_bounded_cortex_log(tmp_path):
    """Routine diagnostics belong in the cortex tree's log dir, not the prompt area.

    Mirrors `mcp-servers/loop-gov-mcp.py`: a bounded file under `~/.hermes-cortex/logs/`
    (here overridden by CORTEX_CONTEXT_LOG), stderr kept for failures, and a logging
    failure that can never break the hook.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available — cannot execute the extension")
    log = tmp_path / "pi-context.log"

    ok = _run_pi_guard(node, HARNESS_DIR / "pi", {"CORTEX_CONTEXT_LOG": str(log)})
    assert ok.returncode == 0, f"{ok.stdout}\n{ok.stderr}"
    assert log.exists(), "the routine trace wrote no log file"
    body = log.read_text()
    assert "CORTEX_RESUME" in body, body
    assert not _routine_stderr_lines(ok.stderr), (
        "the trace is still on the prompt area:\n" + ok.stderr)

    # Bounded: with a 1-byte cap every append rotates, so a sibling appears and the
    # live file never grows past a single line.
    tiny = tmp_path / "tiny.log"
    rolled = _run_pi_guard(node, HARNESS_DIR / "pi",
                           {"CORTEX_CONTEXT_LOG": str(tiny), "CORTEX_CONTEXT_LOG_MAX_BYTES": "1"})
    assert rolled.returncode == 0, f"{rolled.stdout}\n{rolled.stderr}"
    assert (tmp_path / "tiny.log.1").exists(), "the log is unbounded — no rotation happened"
    assert tiny.stat().st_size < 512, "the live log exceeded its cap"

    # Non-fatal: an unusable sink must not break the hook.
    unusable = _run_pi_guard(node, HARNESS_DIR / "pi", {"CORTEX_CONTEXT_LOG": str(tmp_path)})
    assert unusable.returncode == 0, (
        "an unusable log sink broke the extension:\n" + unusable.stdout + unusable.stderr)


def test_macos_parity_for_the_context_layers():
    """macOS is a fleet platform, not an afterthought. Two things break there:

      * the store must NOT shell through `sg docker -c docker exec` (no sg, no
        docker on macOS) — it runs psql directly with a 0600 PGPASSFILE;
      * a hardcoded `python3` is unsafe because it may not be on Pi's PATH
        (Homebrew lives at /opt/homebrew/bin or /usr/local/bin), so the
        interpreter is overridable.
    """
    store_src = (REPO / "ops/services/mycortex-mem/store.py").read_text()
    # The real detector is os.uname().sysname == "Darwin" (checked, not assumed —
    # an earlier version of this assertion demanded sys.platform and failed
    # against correct code: the probe was wrong, not the store).
    assert 'Darwin' in store_src, "store.py needs an explicit macOS branch"
    assert "_is_macos" in store_src, "macOS detection should be resolved once, at init"
    assert "PGPASSFILE" in store_src, "macOS path should use a 0600 PGPASSFILE"
    # And the Linux path must NOT be reachable on macOS.
    assert "sg" in store_src, "Linux path shells through sg"

    # Behavioural, not a string match: force the darwin branch and check the
    # command it builds actually avoids `sg`/`docker`.
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("store_mac_test",
                                        REPO / "ops/services/mycortex-mem/store.py")
    assert spec and spec.loader
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pc = mod.PgConnection()
    pc._is_macos = True
    cmd, env = pc._cmd("mycortex_mem_reader")
    assert "sg" not in cmd and "docker" not in cmd, f"Linux path leaked to macOS: {cmd}"
    assert cmd[0] == "psql" and "-h" in cmd and "localhost" in cmd, cmd
    assert "-w" in cmd, "macOS psql must be --no-password (-w): it must never prompt on /dev/tty"
    assert "PGPASSFILE" in env and env["PGPASSFILE"].endswith(".pgpass"), env
    # The Linux branch must still be the docker one.
    pc._is_macos = False
    cmd_linux, _ = pc._cmd("mycortex_mem_reader")
    assert cmd_linux[0] == "sg" and "docker" in cmd_linux, cmd_linux
    assert "-w" in "".join(cmd_linux), \
        "docker-exec psql must be --no-password (-w): it must never prompt on /dev/tty"

    ext = PI_EXT.read_text()
    assert "CORTEX_CONTEXT_PYTHON" in ext, \
        "the interpreter must be overridable for macOS PATH differences"

    cli_src = CLI_PY.read_text()
    assert cli_src.startswith("#!"), "CLI needs a shebang"
    assert "/usr/bin/env python3" in cli_src.splitlines()[0], \
        "use /usr/bin/env python3 so macOS picks up a Homebrew python"
    for linux_only in ("sg docker", "/proc/", "systemctl", "apt-get"):
        assert linux_only not in cli_src, f"Linux-only construct in the CLI: {linux_only}"


def test_mcp_server_shares_the_implementation():
    """The MCP server must import the shared surface, not define its own."""
    src = MCP_PY.read_text()
    assert "context_tools.py" in src
    assert "def mem_context" not in src and "def session_checkpoint" not in src


def test_plugin_is_an_adapter_not_a_second_implementation():
    """The Hermes plugin must DELEGATE to the shared surface.

    It used to reimplement all five mem_* tools, so `mem_context` existed twice
    — and whichever the runtime resolved, the other silently did not exist. An
    agent then reported "mem_context is broken" and reached for raw SQL. One
    implementation, however many hosts.
    """
    src = (REPO / "plugins/mycortex-mem/__init__.py").read_text()
    assert "_load_context_tools" in src, "plugin must load the shared surface"
    assert "tools.dispatch(" in src, "plugin must dispatch through the shared surface"
    assert "tools.tool_schema_for_mcp(" in src, "schemas must be DERIVED, not hand-written"
    # The hand-written schema list must be gone: that list was the second
    # definition of the same tools.
    assert "PROFILE_SCHEMA, SEARCH_SCHEMA, CONTEXT_SCHEMA" not in src, \
        "hand-written schema list is back — that is the duplicate surface"
    # Exactly one host-local tool is allowed, and it must be documented as such.
    # Compare whitespace-normalised text: prose wraps across lines, so a phrase
    # assertion against raw source fails on a line break (this caught me three
    # times tonight — question the probe before the code).
    flat = " ".join(src.split())
    assert src.count('"mem_reasoning"') >= 1
    assert "host-neutral" in flat, \
        "the host-local exception must say WHY it is local (host-bound capability)"


def test_every_access_layer_funnels_through_one_dispatch():
    """Interop invariant: hosts may differ, semantics may not.

    Each layer must reach the store through context_tools.dispatch — the MCP
    server, the CLI and the plugin alike. A new host means a new ACCESS LAYER,
    never a new implementation.
    """
    layers = {
        "mcp server": (REPO / "mcp-servers/cortex-context-mcp.py").read_text(),
        "cli": CLI_PY.read_text(),
        "plugin": (REPO / "plugins/mycortex-mem/__init__.py").read_text(),
    }
    for name, src in layers.items():
        assert "context_tools" in src, f"{name} does not reference the shared surface"
    assert "tools.dispatch(" in layers["mcp server"] or "tools.dispatch(" in layers["cli"], \
        "MCP/CLI must dispatch, not reimplement"


# ── The harness registry ─────────────────────────────────────────

def test_registry_is_valid_and_every_entry_is_complete():
    reg = yaml.safe_load(REGISTRY.read_text())
    assert reg["harnesses"], "registry declares no harnesses"
    names = [h["name"] for h in reg["harnesses"]]
    assert len(names) == len(set(names)), "duplicate harness name"
    for h in reg["harnesses"]:
        assert h["layer"] in {"mcp", "cli-extension", "cli-hook", "none"}
        assert h.get("why"), f"{h['name']}: needs a why (the evidence for the layer)"
        if h["layer"] != "none":
            assert h.get("surface") and h.get("install") and h.get("verify"), \
                f"{h['name']}: incomplete entry — an unverifiable instruction ships broken"


def test_generated_harness_docs_are_current():
    """CI-style parity: the derived docs must match the registry exactly."""
    r = subprocess.run([sys.executable, str(HARNESS_DIR / "generate-harnesses.py"), "--check"],
                       capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, f"stale derived files:\n{r.stdout}{r.stderr}"


def test_generated_docs_refuse_hand_editing():
    index = (HARNESS_DIR / "INDEX.md").read_text()
    assert "GENERATED" in index.splitlines()[0]
    for h in yaml.safe_load(REGISTRY.read_text())["harnesses"]:
        doc = HARNESS_DIR / h["name"] / "README.md"
        assert doc.is_file(), f"missing generated doc for {h['name']}"
        assert "GENERATED" in doc.read_text().splitlines()[0]


def test_every_harness_names_its_access_layer_in_its_doc():
    reg = yaml.safe_load(REGISTRY.read_text())
    for h in reg["harnesses"]:
        text = (HARNESS_DIR / h["name"] / "README.md").read_text()
        assert f"`{h['layer']}`" in text


def test_steadfaste_is_declared_blocked_not_silently_absent():
    """An unsupported harness must be VISIBLE with its reason, so nobody
    assumes it was simply overlooked."""
    reg = yaml.safe_load(REGISTRY.read_text())
    entries = {h["name"]: h for h in reg["harnesses"]}
    assert "steadfaste-tui" in entries
    assert entries["steadfaste-tui"]["layer"] == "none"
    assert entries["steadfaste-tui"]["why"].strip()
