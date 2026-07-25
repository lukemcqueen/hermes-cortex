"""
Fix actions — auto-fix all discovered issues.

Provides _run_fix() helper and apply_fixes() which iterates over
check results and runs the appropriate fix command for each issue.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from .config import (
    HOME,
    CORTEX_REPO,
    CORTEX_HOME,
    HERMES_HOME,
    CONFIG_FILE,
    INSTALL_CRONS,
    CORTEX_UPDATE,
    INSTALL_SCRIPT,
    INSTALL_OLLAMA,
    SYMLINK_AUDIT,
    MCP_SERVERS_DIR,
    EXPECTED_MCP_SERVERS,
    CURL,
)
from .helpers import run, run_bg


def _run_fix(description, cmd, timeout=120):
    """Helper: print description, run command, return True on success."""
    print(f"  → {description}...")
    out, code = run(cmd, timeout=timeout)
    if code == 0:
        print(f"  ✅ Done")
        return True
    else:
        print(f"  ❌ Failed (exit {code})")
        if out:
            for line in out.split("\n")[:5]:
                print(f"     {line}")
        return False


def apply_fixes(res):
    """Attempt to auto-fix every issue found."""
    if not res.json_mode:
        print("\n  ── Auto-fix ──\n")

    fixed = 0
    failed = 0
    fix_map = {c["name"]: c["status"] for c in res.checks}

    # Fix: missing crons → install-crons.sh
    if any("Crons missing" in k for k in fix_map):
        if _run_fix("Recreating missing crons", ["bash", str(INSTALL_CRONS), "--force"]):
            fixed += 1
        else:
            failed += 1

    # Fix: missing scripts → cortex-update.sh
    if any(k.startswith("Script") for k in fix_map):
        if _run_fix("Deploying scripts via cortex-update", ["bash", str(CORTEX_UPDATE), "--force-all"]):
            fixed += 1
        else:
            failed += 1

    # Fix: MCP server not configured
    for name, server_script in EXPECTED_MCP_SERVERS.items():
        if f"MCP server ({name})" in fix_map and fix_map[f"MCP server ({name})"] == "FAIL":
            if CONFIG_FILE.exists() and CORTEX_REPO.exists():
                mcp_path = MCP_SERVERS_DIR / server_script
                venv_python = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python3"
                if mcp_path.exists() and venv_python.exists():
                    if _run_fix(
                        f"Adding MCP server {name} to config.yaml (venv Python)",
                        [
                            "python3",
                            "-c",
                            f"""
import yaml, sys
with open('{CONFIG_FILE}') as f:
    cfg = yaml.safe_load(f)
if 'mcpServers' not in cfg:
    cfg['mcpServers'] = {{}}
cfg['mcpServers']['{name}'] = {{
    'command': '{venv_python}',
    'args': ['{mcp_path}'],
    'enabled': True
}}
with open('{CONFIG_FILE}', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False)
print('ADDED')
""",
                        ],
                    ):
                        fixed += 1
                    else:
                        failed += 1

    # Fix: MCP server uses bare python3 instead of venv
    for name in EXPECTED_MCP_SERVERS:
        if f"MCP Python ({name})" in fix_map and fix_map[f"MCP Python ({name})"] == "WARN":
            venv_python = HERMES_HOME / "hermes-agent" / "venv" / "bin" / "python3"
            if venv_python.exists():
                if _run_fix(f"Updating MCP {name} to use venv Python",
                            ["hermes", "mcp", "update", name, "--command", str(venv_python)]):
                    fixed += 1
                else:
                    failed += 1

    # Fix: governance plugin not installed/symlinked
    if "Governance plugin" in fix_map and fix_map["Governance plugin"] == "FAIL":
        plugin_dir = HERMES_HOME / "plugins" / "governance-enforcer"
        plugin_src = CORTEX_REPO / "plugins" / "hermes-governance-enforcer"
        if plugin_src.exists():
            if _run_fix("Symlinking governance plugin",
                        ["ln", "-sf", str(plugin_src), str(plugin_dir)]):
                fixed += 1
            else:
                failed += 1
        if _run_fix("Enabling governance plugin",
                    ["hermes", "plugins", "enable", "governance-enforcer", "--allow-tool-override"]):
            fixed += 1
        else:
            failed += 1

    # Fix: pre-commit hook not installed
    if "Pre-commit hook" in fix_map and "FAIL" in fix_map.get("Pre-commit hook", ""):
        hook_src = CORTEX_REPO / "src" / "scripts" / "pre-commit-score"
        hook_dest = CORTEX_HOME / "hooks" / "pre-commit"
        if hook_src.exists():
            if _run_fix("Installing pre-commit hook to shared hooks dir",
                        ["cp", str(hook_src), str(hook_dest)]):
                if _run_fix("Setting hook as executable",
                            ["chmod", "+x", str(hook_dest)]):
                    fixed += 1
                else:
                    failed += 1
            else:
                failed += 1

    # Fix: global hooksPath not set correctly
    if "Global hooksPath" in fix_map and fix_map.get("Global hooksPath") in ("FAIL", "WARN"):
        expected_hooks_path = str(CORTEX_HOME / "hooks")
        if _run_fix("Setting global hooksPath",
                    ["git", "config", "--global", "core.hooksPath", expected_hooks_path]):
            fixed += 1
        else:
            failed += 1

    # Fix: pre-push hook not installed
    if "Pre-push hook" in fix_map and "not installed" in fix_map.get("Pre-push hook", ""):
        push_src = CORTEX_REPO / "src" / "scripts" / "pre-push-pull"
        push_dest = CORTEX_HOME / "hooks" / "pre-push"
        if push_src.exists():
            if _run_fix("Installing pre-push hook",
                        ["cp", str(push_src), str(push_dest)]):
                if _run_fix("Setting hook as executable",
                            ["chmod", "+x", str(push_dest)]):
                    fixed += 1
                else:
                    failed += 1
            else:
                failed += 1

    # Fix: stale governance locks
    state_dir = CORTEX_HOME / "state"
    if state_dir.exists():
        for lf in state_dir.glob(".governance-*.json"):
            try:
                lock_data = json.loads(lf.read_text())
                started = lock_data.get("started_at", "")
                if started:
                    try:
                        started_ts = datetime.fromisoformat(started).timestamp()
                        age_hours = (time.time() - started_ts) / 3600
                        if age_hours > 24:
                            lf.unlink()
                            print(f"  → Removing stale lock: {lf.name} ({age_hours:.0f}h old)")
                            print(f"  ✅ Done")
                            fixed += 1
                    except (ValueError, TypeError):
                        lf.unlink()
                        print(f"  → Removing unparseable lock: {lf.name}")
                        print(f"  ✅ Done")
                        fixed += 1
                else:
                    lf.unlink()
                    print(f"  → Removing lock with no timestamp: {lf.name}")
                    print(f"  ✅ Done")
                    fixed += 1
            except (json.JSONDecodeError, OSError):
                lf.unlink()
                print(f"  → Removing corrupt lock: {lf.name}")
                print(f"  ✅ Done")
                fixed += 1

    # Fix: Ollama down
    if "Ollama" in fix_map and fix_map["Ollama"] == "FAIL":
        if _run_fix("Starting Ollama", ["systemctl", "--user", "start", "ollama"], timeout=10):
            time.sleep(2)
            out2 = run_bg([CURL, "-s", "http://localhost:11434/api/tags", "--max-time", "5"])
            if out2:
                fixed += 1
            else:
                failed += 1
        else:
            if _run_fix("Starting Ollama directly (ollama serve)", ["ollama", "serve"], timeout=5):
                time.sleep(2)
                fixed += 1
            else:
                failed += 1

    # Fix: symlinks need attention
    if "Symlinks" in fix_map and fix_map["Symlinks"] == "WARN":
        if SYMLINK_AUDIT.exists():
            if _run_fix("Running symlink audit", ["bash", str(SYMLINK_AUDIT)]):
                fixed += 1
            else:
                failed += 1

    # Fix: install footprint missing → run install.sh core
    if any(k.startswith("Install (") for k in fix_map):
        if INSTALL_SCRIPT.exists():
            if _run_fix("Running install.sh core components",
                        ["bash", str(INSTALL_SCRIPT), "--quick"]):
                fixed += 1
            else:
                failed += 1

    # Fix: model context (only if 3b variant detected below threshold)
    if INSTALL_OLLAMA.exists():
        out = run_bg([CURL, "-s", "http://localhost:11434/api/tags", "--max-time", "5"])
        if out:
            try:
                models = json.loads(out).get("models", [])
                for m in models:
                    mname = m.get("name", "")
                    if "qwen2.5-coder:3b" in mname or mname == "qwen2.5-coder:3b":
                        if _run_fix(f"Checking context for {mname}",
                                    ["bash", str(INSTALL_OLLAMA), "build_qwen", mname]):
                            fixed += 1
                        break
            except (json.JSONDecodeError, KeyError):
                pass

    # Fix: redundant local git hooks → remove them
    redundant_hooks = [k for k in fix_map if k.startswith("Redundant hook")]
    if redundant_hooks:
        for check_name in redundant_hooks:
            # Extract the hook filepath from the check result
            for c in res.checks:
                if c["name"] == check_name:
                    detail = c.get("detail", "")
                    # Detail format: "/path/to/hook → /target — ignored by git..."
                    path_part = detail.split(" — ")[0] if " — " in detail else detail
                    # Take just the local hook filepath (before " → ")
                    local_hook = path_part.split(" → ")[0].strip() if " → " in path_part else path_part.strip()
                    if local_hook:
                        hook_path = Path(local_hook)
                        if hook_path.exists():
                            if _run_fix(f"Removing redundant hook: {hook_path.name}",
                                        ["rm", "-f", str(hook_path)]):
                                fixed += 1
                            else:
                                failed += 1
                    break

    if not res.json_mode:
        print(f"\n  Auto-fix: {fixed} fixed, {failed} failed\n")

    return fixed, failed
