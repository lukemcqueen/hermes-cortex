"""Every code asset a skill ships must at least PARSE.

A skill tells the agent to run `scripts/foo.py`; if that file has a SyntaxError,
the playbook is broken and the agent finds out at the worst moment. This is also
what makes the pre-commit TDD gate satisfiable for RECOVERED skill assets: the
gate refuses an added code file with no test in the same commit (structural, no
bypass flag), so landing a skill's script that only ever existed on the deployed
copy needs a real guard beside it — not an unrelated test staged to please it.

Discovery-based on purpose: one traversal over the tree, so a newly recovered
asset is covered the moment it lands and the list cannot drift from the suite.
The test FAILS LOUDLY when it finds nothing, so it can never pass vacuously.

Run: bash tests/run-tests.sh tests/test_skill_code_assets_parse.py -q
"""

import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[1] / "skills"

# Code extensions a skill may ship. Shell is included even though the TDD gate
# does not list it: a syntax error there breaks the agent just the same.
PY_EXTS = (".py",)
NODE_EXTS = (".mjs", ".js", ".cjs")
SH_EXTS = (".sh", ".bash")


def _assets(exts):
    """One traversal: every code asset under a skill dir, by extension."""
    if not SKILLS.is_dir():
        return []
    return sorted(p for p in SKILLS.rglob("*") if p.is_file() and p.suffix in exts)


def test_the_traversal_finds_assets():
    """A vacuous pass is the failure mode this guards: prove it saw something."""
    total = sum(len(_assets(e)) for e in (PY_EXTS, NODE_EXTS, SH_EXTS))
    assert total > 0, f"found no code assets under {SKILLS} — the traversal is wrong"


def test_no_family_is_silently_unchecked():
    """A family WITH assets but no way to check them must SAY so.

    A check that cannot run is a third outcome, not a pass: silently skipping the
    node family would make this guard look like it covered everything while the
    JS assets went unverified — the same "green over nothing" shape that let 30
    refused SKILL.md files sit unnoticed.
    """
    families = (("python", PY_EXTS, sys.executable),
                ("shell", SH_EXTS, "bash"),
                ("node", NODE_EXTS, "node"))
    for label, exts, tool in families:
        found = _assets(exts)
        if not found:
            continue
        if tool == sys.executable or shutil.which(tool):
            continue
        pytest.skip(f"{label}: {len(found)} asset(s) present and NO {tool} on PATH "
                    f"— those assets are NOT checked on this host")


@pytest.mark.parametrize("asset", _assets(PY_EXTS), ids=lambda p: str(p.relative_to(SKILLS)))
def test_python_assets_compile(asset):
    try:
        py_compile.compile(str(asset), doraise=True, cfile=str(asset) + ".pyc-check")
    except py_compile.PyCompileError as e:
        pytest.fail(f"{asset.relative_to(SKILLS)} does not compile: {e}")
    finally:
        Path(str(asset) + ".pyc-check").unlink(missing_ok=True)


@pytest.mark.parametrize("asset", _assets(SH_EXTS), ids=lambda p: str(p.relative_to(SKILLS)))
def test_shell_assets_parse(asset):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("no bash on PATH — shell assets NOT checked on this host")
    r = subprocess.run([bash, "-n", str(asset)], capture_output=True, text=True)
    assert r.returncode == 0, f"{asset.relative_to(SKILLS)}: {r.stderr.strip()}"


@pytest.mark.parametrize("asset", _assets(NODE_EXTS), ids=lambda p: str(p.relative_to(SKILLS)))
def test_node_assets_parse(asset):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node on PATH — JS assets NOT checked on this host")
    r = subprocess.run([node, "--check", str(asset)], capture_output=True, text=True)
    assert r.returncode == 0, f"{asset.relative_to(SKILLS)}: {r.stderr.strip()}"
