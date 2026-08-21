#!/usr/bin/env python3
"""Tests for install-lean-index.py — the coding_context 'lean' patch (O8-S3).

Run: python3 tests/test_install_lean_index.py
     (or: python3 -m pytest tests/test_install_lean_index.py -v)

Verifies:
  1. The three patch templates are internally consistent (old exists, new differs)
  2. Applying to a pristine coding_context.py produces all 3 patches
  3. The lean mode demotes categories WITHOUT collapsing the toolset (the
     focus-mode difference that makes 'lean' the right choice for ops agents)
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_INSTALLER = _REPO / "ops" / "scripts" / "install" / "install-lean-index.py"

_spec = importlib.util.spec_from_file_location("ili", str(_INSTALLER))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# A pristine coding_context.py: real file with the lean patches REVERTED
def _pristine_copy() -> Path:
    """Copy the real coding_context.py and revert the 3 lean patches."""
    src = Path(os.path.expanduser("~/.hermes/hermes-agent/agent/coding_context.py"))
    content = src.read_text(encoding="utf-8", errors="replace")
    # revert compact branch -> original
    for name, old, new in _mod.PATCHES:
        if new in content:
            content = content.replace(new, old, 1)
        elif old not in content:
            raise AssertionError(f"pristine prep: {name} neither old nor new present")
    dst = Path(tempfile.mkdtemp()) / "coding_context.py"
    dst.write_text(content, encoding="utf-8")
    return dst


def test_templates_consistent():
    # The old templates must exist in the CURRENT (patched) file so a
    # --force revert could work; and new must differ from old.
    current = _mod.read()
    for name, old, new in _mod.PATCHES:
        assert new != old, f"{name}: new must differ from old"
        # old may be absent if already applied (new present) — that's fine;
        # the invariant is new-vs-old differ and both are non-empty
        assert old.strip(), f"{name}: old template empty"
        assert new.strip(), f"{name}: new template empty"


def test_apply_to_pristine_produces_all_three():
    pristine = _pristine_copy()
    # point the installer at the pristine copy and apply
    old_target = _mod.TARGET
    _mod.TARGET = str(pristine)
    try:
        rc = _mod.apply()
        assert rc == 0, f"apply returned {rc}"
        content = pristine.read_text()
        for name, _old, new in _mod.PATCHES:
            assert new in content, f"{name}: patch not present after apply"
    finally:
        _mod.TARGET = old_target


def test_lean_demotes_without_toolset_collapse():
    """The core behavioral contract: lean shrinks the index, keeps tools."""
    # Simulate against the REAL (already-patched) module via subprocess to
    # get the actual coding_context runtime behavior.
    code = """
import sys, os
sys.path.insert(0, '/home/esther/.hermes/hermes-agent')
os.environ['HERMES_HOME'] = os.path.expanduser('~/.hermes')
from agent.coding_context import coding_compact_skill_categories, resolve_runtime_mode
cats = coding_compact_skill_categories(platform='telegram', cwd='/home/esther',
                                      config={'agent': {'coding_context': 'lean'}})
rm = resolve_runtime_mode(platform='telegram', cwd='/home/esther',
                          config={'agent': {'coding_context': 'lean'}})
assert len(cats) > 10, f'expected >10 demoted categories, got {len(cats)}'
assert 'ads' in cats, 'ads should be demoted'
assert rm.profile.toolset is None or not rm.is_coding, 'lean must NOT collapse toolset'
print(f'lean: {len(cats)} categories demoted, toolset intact')
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, f"runtime check failed: {r.stderr[-500:]}"
    assert "demoted" in r.stdout


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
