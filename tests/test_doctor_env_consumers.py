#!/usr/bin/env python3
"""The doctor's .env consumer scan must look where the consumers actually ARE.

Measured 2026-10-13: four `Config (X) — defined but zero consumer scripts reference it` INFO
items for JUDGE_MODEL / EMBEDDING_MODEL / CODING_MODEL / CREATIVE_MODEL. Three of them were
false: the scan iterated `CORTEX_REPO/ops/scripts` NON-recursively, while the consumers live in
`ops/scripts/manage/`, `ops/offline/` and `mcp-servers/`. A check that cannot see its input
reports the input as missing — the same shape as a checker with no parser blaming the artifact.

Run: python3 -m pytest tests/test_doctor_env_consumers.py -q
"""
import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_CONFIG = _REPO / "ops" / "scripts" / "manage" / "cortex_doctor" / "config.py"

if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))


def _load():
    spec = importlib.util.spec_from_file_location("doctor_config_under_test", _CONFIG)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_repo(tmp_path):
    """A miniature repo: consumers at three depths, plus the two things to ignore."""
    (tmp_path / "ops" / "scripts" / "manage").mkdir(parents=True)
    (tmp_path / "ops" / "scripts" / "top.py").write_text(
        'MODEL = get_model("EMBEDDING_MODEL", "nomic")\n')
    (tmp_path / "ops" / "scripts" / "manage" / "judge.py").write_text(
        'JUDGE_MODEL = get_model("JUDGE_MODEL", "qwen2.5:3b")\n')
    (tmp_path / "mcp-servers").mkdir()
    (tmp_path / "mcp-servers" / "loop-gov-mcp.py").write_text(
        'NOMIC_MODEL = get_model("EMBEDDING_MODEL", "nomic")\n')
    # ignored: a compiled cache and a test file (a test is not a consumer)
    (tmp_path / "ops" / "scripts" / "__pycache__").mkdir()
    (tmp_path / "ops" / "scripts" / "__pycache__" / "ghost.py").write_text("CODING_MODEL\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_models.py").write_text("CODING_MODEL\n")
    return tmp_path


def test_consumers_are_found_below_the_top_level_and_in_sibling_trees(tmp_path):
    repo = _fake_repo(tmp_path)
    c = _load()
    found = c.find_script_consumers([repo / "ops", repo / "mcp-servers"])
    assert "top.py" in found["EMBEDDING_MODEL"], found
    assert "loop-gov-mcp.py" in found["EMBEDDING_MODEL"], found
    assert "judge.py" in found["JUDGE_MODEL"], found
    print("  consumers below the top level and in sibling trees are found ✓")


def test_caches_and_tests_are_not_consumers(tmp_path):
    repo = _fake_repo(tmp_path)
    c = _load()
    found = c.find_script_consumers([repo / "ops", repo / "mcp-servers", repo / "tests"])
    assert found["CODING_MODEL"] == [], found["CODING_MODEL"]
    print("  __pycache__ and test files are not consumers ✓")


def test_a_docstring_mention_is_not_a_consumer(tmp_path):
    """Naming a variable in a docstring is documentation, not consumption. Counting it certified
    CREATIVE_MODEL — documented as "reserved ... (no default yet)" and read by nothing."""
    tree = tmp_path / "ops"
    (tree / "scripts").mkdir(parents=True)
    (tree / "scripts" / "models.py").write_text(
        '"""Model contract.\n\n  CREATIVE_MODEL — Reserved for creative/text generation.\n"""\n')
    (tree / "scripts" / "real.py").write_text('M = get_model("CREATIVE_MODEL", "x")\n')
    c = _load()
    found = c.find_script_consumers([tree])
    assert found["CREATIVE_MODEL"] == ["real.py"], found["CREATIVE_MODEL"]
    print("  a docstring mention is not a consumer ✓")


def test_shell_and_environ_reads_are_consumers(tmp_path):
    tree = tmp_path / "ops"
    tree.mkdir()
    (tree / "env.sh").write_text('MODEL="${EMBEDDING_MODEL:-nomic-embed-text:v1.5}"\n')
    (tree / "plain.sh").write_text('MODEL=$JUDGE_MODEL\n')
    (tree / "py.py").write_text('m = os.environ.get("CODING_MODEL")\n')
    (tree / "bracket.py").write_text('m = os.environ["CREATIVE_MODEL"]\n')
    c = _load()
    found = c.find_script_consumers([tree])
    assert found["EMBEDDING_MODEL"] == ["env.sh"], found["EMBEDDING_MODEL"]
    assert found["JUDGE_MODEL"] == ["plain.sh"], found["JUDGE_MODEL"]
    assert found["CODING_MODEL"] == ["py.py"], found["CODING_MODEL"]
    assert found["CREATIVE_MODEL"] == ["bracket.py"], found["CREATIVE_MODEL"]
    print("  shell and os.environ reads are consumers ✓")


def test_the_repo_trees_that_hold_consumers_are_searched():
    """Roots derived from THIS repo, never the ambient HOME: the first version used the default
    roots and its sibling failed inside the full suite, where another module's HOME is in effect."""
    c = _load()
    found = c.find_script_consumers([_REPO / "ops", _REPO / "core", _REPO / "mcp-servers"])
    assert found["EMBEDDING_MODEL"], "no EMBEDDING_MODEL consumer found in the real repo"
    assert found["JUDGE_MODEL"], "no JUDGE_MODEL consumer found in the real repo"
    assert found["CODING_MODEL"], "no CODING_MODEL consumer found in the real repo"
    assert "agent-llm-judge-scorer.py" in found["JUDGE_MODEL"], found["JUDGE_MODEL"]
    print(f"  real repo: EMBEDDING_MODEL={len(found['EMBEDDING_MODEL'])} "
          f"JUDGE_MODEL={len(found['JUDGE_MODEL'])} CODING_MODEL={len(found['CODING_MODEL'])} "
          f"CREATIVE_MODEL={len(found['CREATIVE_MODEL'])} ✓")


def test_the_default_roots_are_the_repo_script_trees():
    """The default call is the one the doctor makes; assert it covers ops/, core/ and
    mcp-servers/ (structurally — the ambient paths are not this host's under a full suite)."""
    import inspect
    src = inspect.getsource(_load().find_script_consumers)
    for needle in ('CORTEX_REPO / "ops"', 'CORTEX_REPO / "core"', 'CORTEX_REPO / "mcp-servers"'):
        assert needle in src, f"default roots must include {needle}"
    print("  the default roots are the repo's ops/core/mcp-servers trees ✓")


def test_the_doctor_package_itself_is_not_a_consumer():
    """The doctor's own `known_vars` list MENTIONS every variable — counting it made the check
    certify itself, and turned CREATIVE_MODEL (which has no real consumer) into a PASS."""
    c = _load()
    found = c.find_script_consumers([_REPO / "ops", _REPO / "core", _REPO / "mcp-servers"])
    for var, names in found.items():
        assert "config.py" not in names, (var, names)
        assert "checks.py" not in names, (var, names)
    print("  the doctor's own package is not counted as a consumer ✓")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
