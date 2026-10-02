#!/usr/bin/env python3
"""harness.py — `hc harness`: wire any coding agent to the cortex context store.

WHY THIS EXISTS: the fleet will consume ONE capability from N heterogeneous
coding agents (Pi, Hermes, Claude Code, Codex, …). That knowledge was already
written down once — `ops/install/harnesses/registry.yaml` — but acting on it
meant a developer hand-copying an extension and hand-typing a tool allowlist.
Hand-typed lists rot: the tool surface grows in `context_tools.TOOLS` and the
`--tools` literal in the registry quietly stops matching, so Pi loses a tool
while everything still looks wired.

This command is a DRIVER over the registry, never a second definition of it:
it reads the registry, executes the declared install operations, and DERIVES
the run line's tool list from the contract — so adding a tool to the contract
changes what `hc harness install pi` prints with no registry edit.

    hc harness list                 what is declared, and its layer
    hc harness show <name>          install / run / verify for one harness
    hc harness install <name> [--dir DIR]
                                    do the file steps, print the run line
    hc harness verify [<name>]      registry current? store reachable? artifact there?
    hc harness add <name> --layer mcp|cli-extension|cli-hook|none --surface '...'

Layers (same four the registry declares):
  mcp            harness reads an MCP server from its own config — we print the
                 registration entry and NEVER edit that harness's config file
  cli-extension  no MCP client; install copies the shipped artifact, run line is
                 generated with the full derived `--tools` surface (Pi)
  cli-hook       only needs the lifecycle trigger run at a boundary
  none           declared unsupported, with the reason — visible, not silent

Design: docs/design/agent-interop.md · Runbook: docs/runbooks/context-integration.md
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("hc harness: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)

HERE = Path(__file__).resolve().parent          # repo: <repo>/ops/scripts/hc


def registry_dir() -> Path:
    """Where registry.yaml lives: override, repo layout, or deployed layout.

    The deployed harness.py is FLAT (`~/.hermes-cortex/scripts/hc-harness.py`)
    because `scripts/hc` is the launcher file — so this must not assume a
    directory shape. Every candidate is checked, and the last one is only a
    fallback for the error message.
    """
    override = os.environ.get("CORTEX_HARNESS_DIR")
    candidates = [
        Path(override) if override else None,
        HERE.parents[1] / "install" / "harnesses",                        # repo: ops/install/harnesses
        Path.home() / "hermes-cortex" / "ops" / "install" / "harnesses",
        Path.home() / "hermes-cortex" / "harnesses",
        Path.home() / ".hermes-cortex" / "ops" / "install" / "harnesses",
        Path.home() / ".hermes-cortex" / "harnesses",                     # deployed
    ]
    for c in candidates:
        if c and (c / "registry.yaml").is_file():
            return c
    return HERE.parents[1] / "install" / "harnesses"


def contract_tools_py() -> Path | None:
    """The ONE implementation, as a file: repo layout first, then deployed."""
    candidates = [
        Path(os.environ["CORTEX_CONTEXT_TOOLS"]) if os.environ.get("CORTEX_CONTEXT_TOOLS") else None,
        HERE.parents[1] / "services" / "mycortex-mem" / "context_tools.py",   # repo: ops/services
        Path.home() / "hermes-cortex" / "ops" / "services" / "mycortex-mem" / "context_tools.py",
        Path.home() / ".hermes-cortex" / "services" / "mycortex-mem" / "context_tools.py",
    ]
    for p in candidates:
        if p and p.is_file():
            return p
    return None


def context_cli() -> Path | None:
    """The shared CLI adapter (cortex-context.py): repo layout first, then deployed."""
    candidates = [
        Path(os.environ["CORTEX_CONTEXT_CLI"]) if os.environ.get("CORTEX_CONTEXT_CLI") else None,
        HERE.parents[1] / "cortex-context.py",                                # repo: ops/scripts
        Path.home() / "hermes-cortex" / "ops" / "scripts" / "cortex-context.py",
        Path.home() / ".hermes-cortex" / "scripts" / "cortex-context.py",
    ]
    for p in candidates:
        if p and p.is_file():
            return p
    return None



def load_registry() -> dict:
    reg = registry_dir() / "registry.yaml"
    if not reg.is_file():
        print(f"hc harness: registry.yaml not found (looked in {registry_dir()})",
              file=sys.stderr)
        sys.exit(1)
    try:
        data = yaml.safe_load(reg.read_text()) or {}
    except yaml.YAMLError as exc:
        print(f"hc harness: registry is not valid YAML — fix it first.\n  {reg}\n  {exc}",
              file=sys.stderr)
        sys.exit(1)
    if not isinstance(data.get("harnesses"), list) or not data["harnesses"]:
        print("hc harness: registry declares no harnesses", file=sys.stderr)
        sys.exit(1)
    return data


def find(reg: dict, name: str) -> dict | None:
    return next((h for h in reg["harnesses"] if h.get("name") == name), None)


def contract_tool_names() -> list[str]:
    """The ONE implementation's tool surface — the source the run line derives from."""
    p = contract_tools_py()
    if p is None:
        return []
    spec = importlib.util.spec_from_file_location("hc_harness_context_tools", p)
    if spec is None or spec.loader is None:
        return []
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [t["name"] for t in mod.TOOLS]


def artifact_tool_names(h: dict) -> list[str]:
    """The tools a cli-extension artifact actually registers.

    The `--tools` allowlist must name tools that EXIST in the harness, so the
    line is the contract INTERSECTED with what the artifact registers — never the
    whole contract (which would advertise a tool Pi cannot call) and never a
    hand-typed literal (which silently rots when the contract grows). The parsing
    is the same shape `tests/test_context_harnesses.py` already pins.
    """
    artifact = h.get("artifact")
    if not artifact:
        return []
    p = registry_dir() / h["name"] / artifact
    if not p.is_file():
        return []
    import re
    return sorted(set(re.findall(r'tool\(\s*"([a-z_]+)"', p.read_text())))


def derived_run_line(h: dict) -> tuple[str, list[str]] | None:
    """(run line, contract tools this harness does NOT expose).

    `--tools` is derived from the contract ∩ the artifact's registrations. The
    second element is returned so a caller can report the gap LOUDLY instead of
    letting a tool quietly not exist in the harness.
    """
    base = list(h.get("tools_base") or [])
    if not base:
        return None
    names = contract_tool_names()
    if not names:
        return None
    registered = artifact_tool_names(h)
    exposed = [n for n in names if n in registered] if registered else list(names)
    unexposed = [n for n in names if registered and n not in registered]
    ext = h.get("artifact")
    return f"pi -e {ext} --tools {','.join(base + exposed)}", unexposed


# ── commands ────────────────────────────────────────────────────

def cmd_list(reg: dict) -> int:
    order = {"shipped": 0, "documented": 1, "blocked": 2, "planned": 3}
    hs = sorted(reg["harnesses"], key=lambda h: (order.get(h.get("status", "planned"), 9),
                                                 h["name"]))
    print(f"Declared harnesses: {len(hs)}\n")
    print(f"  {'HARNESS':<16} {'LAYER':<14} {'STATUS':<11} SURFACE")
    for h in hs:
        print(f"  {h['name']:<16} {h['layer']:<14} {h.get('status', 'planned'):<11} "
              f"{h.get('surface', 'n/a')}")
    print("\n  hc harness install <name> [--dir DIR]   wire it into a project")
    print("  hc harness verify  [<name>]             prove it, don't assume it")
    return 0


def cmd_show(reg: dict, name: str) -> int:
    h = find(reg, name)
    if h is None:
        return _unknown(name)
    print(f"{h['name']} — layer `{h['layer']}` · status `{h.get('status', 'planned')}` "
          f"· surface `{h.get('surface', 'n/a')}`\n")
    print(f"Why this layer:\n  {h.get('why', '').strip()}\n")
    if h.get("install"):
        print("Install:\n" + "\n".join(f"  {l}" for l in h["install"].strip().splitlines()) + "\n")
    derived = derived_run_line(h)
    if derived:
        print("Run:\n  " + derived[0] + "\n")
        if derived[1]:
            print("  note: contract tools not exposed by this harness: "
                  + ", ".join(derived[1]) + "\n")
    elif h.get("run"):
        print("Run:\n  " + h["run"].strip() + "\n")
    if h.get("verify"):
        print("Verify:")
        for i, v in enumerate(h["verify"], 1):
            print(f"  {i}. {v}")
    return 0


def cmd_install(reg: dict, name: str, target: Path) -> int:
    h = find(reg, name)
    if h is None:
        return _unknown(name)
    layer = h["layer"]
    print(f"hc harness install {name}  →  {target}   (layer: {layer})\n")

    if layer == "none":
        print(f"NOT SUPPORTED — {h.get('why', 'no surface declared').strip()}")
        print("The gap is declared on purpose: a guessed wiring exists and does nothing.")
        return 1

    if layer in ("cli-hook",):
        print("This harness needs no tool surface — wire the lifecycle trigger:")
        print(f"  {reg.get('defaults', {}).get('trigger', 'session-autocheckpoint.py')}")
        return 0

    # File steps (cli-extension today; any layer may declare install_ops later)
    ops = h.get("install_ops") or []
    for op in ops:
        if "mkdir" in op:
            (target / op["mkdir"]).mkdir(parents=True, exist_ok=True)
            print(f"  ✓ mkdir {op['mkdir']}")
        elif "copy" in op:
            src = registry_dir() / op["copy"]["from"]
            dst = target / op["copy"]["to"]
            if not src.is_file():
                print(f"  ✗ missing artifact: {src}", file=sys.stderr)
                return 1
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"  ✓ {op['copy']['to']}  (from {op['copy']['from']})")

    if not ops:
        # No machine-executable steps for this harness: print the declared install
        # prose rather than inventing one. (Layer `mcp`: the config file belongs
        # to the OTHER tool — we hand the developer the entry, never edit it.)
        print("Manual step (this harness owns its own config):")
        print("\n".join(f"  {l}" for l in (h.get("install") or "  (none declared)").strip().splitlines()))

    derived = derived_run_line(h)
    if derived:
        run, unexposed = derived
        print("\nRun (tool list derived from the contract — do not hand-edit):")
        print(f"  {run}")
        if unexposed:
            print(f"  note: this extension does not expose: {', '.join(unexposed)}")
        envs = reg.get("defaults", {}).get("env", [])
        if envs:
            print("\nSession identity (else derived from git, which is usually right):")
            for e in envs:
                val = "pi" if e == "CORTEX_SESSION_HARNESS" else "<value>"
                print(f"  export {e}={val}")

    if h.get("verify"):
        print("\nThen prove it (a copied file is not a working wiring):")
        for i, v in enumerate(h["verify"], 1):
            print(f"  {i}. {v}")
    return 0


def cmd_verify(reg: dict, name: str | None) -> int:
    ok = True

    # 1. Registry + generated docs current
    gen = registry_dir() / "generate-harnesses.py"
    if gen.is_file():
        r = subprocess.run([sys.executable, str(gen), "--check"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            print(f"registry: current — {(r.stdout or '').strip()}")
        else:
            print(f"registry: STALE — {(r.stderr or r.stdout).strip()}")
            ok = False
    else:
        print(f"registry: generator not found at {gen} — cannot check derived docs")
        ok = False

    # 2. Store reachable through the shared CLI
    cli = context_cli()
    if cli is not None:
        r = subprocess.run([sys.executable, str(cli), "mem_context", "{}"],
                           capture_output=True, text=True, timeout=90)
        out = (r.stdout or "") + (r.stderr or "")
        if "memory unavailable" in out:
            print("store: UNREACHABLE — memory unavailable through the CLI")
            ok = False
        elif '"card"' in out or '"error"' in out:
            print("store: reachable")
        else:
            print(f"store: unexpected response — {out.strip()[:200]}")
            ok = False
    else:
        print(f"store: CLI not found at {cli} — cannot check")
        ok = False

    # 3. Artifact present for the named harness
    if name:
        h = find(reg, name)
        if h is None:
            return _unknown(name)
        if h.get("artifact"):
            p = registry_dir() / name / h["artifact"]
            if p.is_file():
                print(f"artifact: {name}/{h['artifact']} present")
            else:
                print(f"artifact: MISSING — {p}")
                ok = False
        run = derived_run_line(h) if h.get("layer") == "cli-extension" else None
        if run and not contract_tool_names():
            print("contract: tool surface not loadable — run line cannot be derived")
            ok = False
        print(f"next: hc harness install {name} --dir <your-project>")

    print("\nresult: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def cmd_add(reg: dict, name: str, layer: str, surface: str) -> int:
    gen = registry_dir() / "generate-harnesses.py"
    if not gen.is_file():
        print(f"hc harness: generator not found at {gen}", file=sys.stderr)
        return 1
    r = subprocess.run([sys.executable, str(gen), "--add", name,
                        "--layer", layer, "--surface", surface],
                       capture_output=True, text=True, timeout=60)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode != 0:
        return r.returncode
    print("\nNEXT (required — a scaffolded entry is not a wired harness):")
    print(f"  1. fill why / install / verify in {registry_dir() / 'registry.yaml'}")
    print(f"  2. {gen} && {gen} --check")
    print(f"  3. hc harness install {name} --dir <your-project>")
    return 0


def _unknown(name: str) -> int:
    print(f"hc harness: unknown harness '{name}' — try: hc harness list", file=sys.stderr)
    return 2


# ── entrypoint ──────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hc harness",
                                 description="Wire a coding agent to the cortex context store.")
    ap.add_argument("cmd", nargs="?", default="list",
                    choices=["list", "show", "install", "verify", "add", "help"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--dir", default=".", help="target project dir (install)")
    ap.add_argument("--layer", default="mcp")
    ap.add_argument("--surface", default="")
    a = ap.parse_args(argv)

    if a.cmd == "help":
        print((__doc__ or "").strip())
        return 0

    reg = load_registry()
    if a.cmd == "list":
        return cmd_list(reg)
    if a.cmd == "show":
        return cmd_show(reg, a.name) if a.name else _unknown("<none>")
    if a.cmd == "install":
        return cmd_install(reg, a.name, Path(a.dir).expanduser().resolve()) if a.name else _unknown("<none>")
    if a.cmd == "verify":
        return cmd_verify(reg, a.name)
    if a.cmd == "add":
        return cmd_add(reg, a.name, a.layer, a.surface) if a.name else _unknown("<none>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
