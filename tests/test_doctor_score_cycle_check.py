#!/usr/bin/env python3
"""The legacy score-cycle CLI is not "old" while live scripts still invoke it.

Measured 2026-10-14: the doctor reported `Old score-cycle found at ~/.local/bin/score-cycle —
current governance uses MCP tools`. That reads as a leftover and invites deletion, but
`pre-commit-score` resolves score-cycle through `~/.local/bin/` (and hard-blocks when none is
found) and `agent-governance-auditor.py` runs it by bare name for auto-remediation. A signal
that calls a WIRED-IN tool "old" is how a working path gets removed.

Run: python3 -m pytest tests/test_doctor_score_cycle_check.py -q
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402


def test_a_script_invoking_the_cli_is_a_consumer(tmp_path):
    tree = tmp_path / "scripts"
    tree.mkdir()
    (tree / "pre-commit-score").write_text(
        'for candidate in score-cycle ~/.local/bin/score-cycle; do :; done\n')
    (tree / "unrelated.sh").write_text("echo hi\n")
    found = checks._score_cycle_consumers([tree])
    assert "pre-commit-score" in found, found
    assert "unrelated.sh" not in found, found
    print("  a script that invokes score-cycle is a consumer ✓")


def test_prose_and_echo_mentions_are_not_consumers(tmp_path):
    """A comment or an `echo` that names the CLI is not wiring. Counting those made the doctor
    list eleven "consumers", most of which only mention the word (2026-10-14)."""
    tree = tmp_path / "scripts"
    tree.mkdir()
    (tree / "installer.sh").write_text(
        '# score-cycle is installed by setup.sh\n'
        'echo "    score-cycle --help"\n'
        'printf "%s\\n" "score-cycle"\n'
        '    """the score-cycle tool is legacy; use the MCP tools"""\n')
    (tree / "test_score_cycle.py").write_text('subprocess.run(["score-cycle"])\n')
    assert checks._score_cycle_consumers([tree]) == []
    print("  prose, echo and test mentions are not consumers ✓")


def test_real_wiring_forms_are_consumers(tmp_path):
    """The forms the fleet actually uses: an argv element, a PATH candidate list, a symlink
    target map, and a resolved path."""
    tree = tmp_path / "scripts"
    tree.mkdir()
    (tree / "auditor.py").write_text('subprocess.run(["score-cycle", "--task", "t"])\n')
    (tree / "pre-commit-score").write_text(
        'for candidate in score-cycle ~/.local/bin/score-cycle; do :; done\n')
    (tree / "setup.sh").write_text('TOOLS["score_cycle.py"]="score-cycle"\n')
    (tree / "verify.sh").write_text('SCORE_CMD="${BIN_DIR}/score-cycle"\n')
    found = checks._score_cycle_consumers([tree])
    assert set(found) == {"auditor.py", "pre-commit-score", "setup.sh", "verify.sh"}, found
    print("  argv, PATH-candidate, symlink-map and resolved-path forms are consumers ✓")


def test_no_consumer_yields_an_empty_list(tmp_path):
    tree = tmp_path / "scripts"
    tree.mkdir()
    (tree / "unrelated.sh").write_text("echo hi\n")
    assert checks._score_cycle_consumers([tree]) == []
    print("  no consumer is reported as no consumer ✓")


def test_the_real_repo_has_consumers():
    """Hermetic: roots derived from THIS repo, never from the ambient HOME. The first version of
    this test called the default roots and passed alone but FAILED inside the full suite, where
    another module's HOME is in effect — a test whose verdict depends on who invoked it."""
    found = checks._score_cycle_consumers([_REPO / "ops", _REPO / "core"])
    assert found, "no consumer found in the repo's own ops/core trees"
    assert "agent-governance-auditor.py" in found, found
    print(f"  repo consumers: {sorted(found)} ✓")


def test_the_default_roots_are_the_fleet_trees():
    """The default call is the one the doctor makes; assert it searches the deployed scripts dir
    and the repo's ops/core trees (structurally — the ambient paths are not this host's under a
    full-suite run)."""
    import inspect
    src = inspect.getsource(checks._score_cycle_consumers)
    for needle in ('CORTEX_HOME / "scripts"', 'CORTEX_REPO / "ops"', 'CORTEX_REPO / "core"'):
        assert needle in src, f"default roots must include {needle}"
    print("  the default roots are the deployed scripts dir + the repo's ops/core trees ✓")


def test_the_check_branches_on_consumers_instead_of_calling_it_old():
    """Source-level pin for the branch that needs a live host to exercise."""
    src = (_REPO / "ops" / "scripts" / "manage" / "cortex_doctor" / "checks.py").read_text()
    i = src.index("Score-cycle CLI (old system)")
    block = src[i:i + 1400]
    assert "_score_cycle_consumers" in block, block[:400]
    assert "still invoked by" in block, "a consumer must change the verdict"
    assert "no script invokes it" in block, "the leftover wording must survive for the real case"
    print("  the check branches on consumers instead of calling a wired tool old ✓")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
