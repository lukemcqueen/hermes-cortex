#!/usr/bin/env python3
"""Tests for the hc-lean-index user plugin — the distinct 'lean' mode.

Replaces the retired ``install-lean-index.py`` core patch, which rewrote
``~/.hermes/hermes-agent/agent/coding_context.py`` and dirtied the upstream git
tree. The plugin now installs lean via a runtime monkeypatch in the user plugin
dir, so no core file is touched.

Verifies:
  1. The plugin installs a distinct 'lean' mode (>10 categories demoted).
  2. lean does NOT collapse the toolset (the focus-mode difference).
  3. The agent git tree is NOT patched (the core edit is gone).
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_PLUGIN = _REPO / "plugins" / "hc-lean-index" / "__init__.py"


def _load_plugin():
    spec = importlib.util.spec_from_file_location("hc_lean_index_test", str(_PLUGIN))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plugin_installs_lean_without_toolset_collapse():
    _load_plugin()  # import performs the install in this process
    code = """
import os, sys
from pathlib import Path
repo = os.environ['HC_REPO']
sys.path.insert(0, str(Path.home() / '.hermes' / 'hermes-agent'))
os.environ.setdefault('HERMES_HOME', os.path.expanduser('~/.hermes'))
import importlib.util
spec = importlib.util.spec_from_file_location('hc_lean_index', os.path.join(repo, 'plugins', 'hc-lean-index', '__init__.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
from agent.coding_context import coding_compact_skill_categories, resolve_runtime_mode
cfg = {'agent': {'coding_context': 'lean'}}
cats = coding_compact_skill_categories(platform='telegram', cwd=str(Path.home()), config=cfg)
rm = resolve_runtime_mode(platform='telegram', cwd=str(Path.home()), config=cfg)
assert len(cats) > 10, f'expected >10 demoted categories, got {len(cats)}'
assert 'ads' in cats, 'ads should be demoted'
assert rm.profile.toolset is None or not rm.is_coding, 'lean must NOT collapse the toolset'
print('lean:', len(cats), 'categories demoted, toolset intact')
"""
    env = dict(os.environ, HC_REPO=str(_REPO))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"runtime check failed: {r.stderr[-800:]}"
    assert "demoted" in r.stdout


def test_agent_tree_not_patched():
    """The retired core patch must NOT be present in the agent checkout."""
    src = Path(os.path.expanduser("~/.hermes/hermes-agent/agent/coding_context.py"))
    if not src.exists():
        return  # no git-installed checkout on this host
    content = src.read_text(encoding="utf-8", errors="replace")
    assert "Local lean-index extension" not in content, "core lean patch must be gone from the agent tree"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
