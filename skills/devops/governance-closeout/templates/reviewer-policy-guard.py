# Guard template for a reviewer-policy change.
#
# Copy into the repo's test tree and point it at the real prompt template and gate module. It pins
# BOTH halves of an authorized policy change: the new scoping rules, and the strict case that must
# survive them. A policy change that ships without the second half can be cited later while
# behavioural proof is quietly dropped.
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "docs" / "templates" / "adversarial-reviewer-prompt.md"
spec = importlib.util.spec_from_file_location("lo_gov_policy", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)
TEXT = TEMPLATE.read_text()


def test_00_preconditions():
    """The things under test must exist, or a failure below is misleading."""
    assert TEMPLATE.is_file(), f"reviewer prompt template missing: {TEMPLATE}"
    assert "=== REVIEWED MATERIAL ===" in TEXT, "not the prompt the gate actually uses"


def test_scoping_rules_are_present():
    assert "scope the demand to the claim" in TEXT
    assert "historical measurement" in TEXT.lower()
    assert "operator directive" in TEXT.lower()
    assert "POINT AT its record" in TEXT


def test_strict_case_survives_the_scoping():
    """THE guard: the relaxation must not have removed behavioural proof."""
    assert "does NOT relax" in TEXT
    assert "committed, re-runnable test or script, in this range" in TEXT
    assert "is `unverified-claim`" in TEXT


def test_sibling_rule_forbids_the_strongest_severity():
    assert "judged on ITS OWN blob" in TEXT
    assert "as `fabrication`" in TEXT and "do not" in TEXT
    assert "YOUR WINDOW" in TEXT


def test_material_names_the_range_so_the_rule_can_be_applied():
    """A rule the reviewer cannot apply is aspirational: the material must name siblings."""
    saved_r, saved_g = mcp._push_range_blobs, mcp._git_capture
    mcp._push_range_blobs = lambda repo: {"a/one.py": "1" * 40, "b/two.py": "2" * 40}
    mcp._git_capture = lambda repo, *a: ""
    try:
        material = mcp._blob_material(Path("/tmp"), "base", "b/two.py", {
            "sid": "s", "author": "a", "branch": "b", "head_sha": "h",
            "cycle_id": 1, "task_id": "t", "description": "d"})
    finally:
        mcp._push_range_blobs, mcp._git_capture = saved_r, saved_g
    assert "a/one.py" in material, "sibling paths must reach the reviewer"
    assert "SIBLING claim" in material, "the instruction must travel with the material"
