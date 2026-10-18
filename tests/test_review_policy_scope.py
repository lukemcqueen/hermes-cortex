#!/usr/bin/env python3
"""The reviewer's demands must be scoped to the claim — without relaxing the strict case.

Operator authorization (Luke, 2026-10-18): "As long as the suggested rule does not lessen
governance then go for it." Two rules were added to the reviewer's constitution, and this file is
what makes that condition checkable rather than a promise:

  A. the reviewer prompt states the PROOF-SCOPING rule — behavioural claims still require a
     committed, re-runnable test (the strict case, explicit and unchanged); a historical
     measurement or an operator directive requires a POINTER to its record, because those cannot
     be test fixtures (the behaviour measured no longer exists; a quoted instruction is a fact);
  B. the reviewer prompt states the SIBLING rule — a file that leans on another file in the same
     range must be reported at most as info and left to that file's own blob, never as fabrication;
  C. the per-blob material NAMES the range's other files, so the sibling rule is actionable;
  D. the material is unchanged when the file has no siblings (no stray block);
  E. NO RELAXATION: the strict requirements are still present verbatim, so a later edit cannot
     quietly drop behavioural proof while citing this policy.

Everything is read from the shipped files, so a future edit that removes a rule fails here.
"""
import importlib.util
import logging as _logging
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "docs" / "templates" / "adversarial-reviewer-prompt.md"
spec = importlib.util.spec_from_file_location("loop_gov_policy", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)

_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)

TEXT = TEMPLATE.read_text()


def test_00_preconditions():
    assert TEMPLATE.is_file(), f"the reviewer's prompt template is missing: {TEMPLATE}"
    assert "=== REVIEWED MATERIAL ===" in TEXT, (
        "the template no longer carries its material marker — this is not the prompt the gate uses")
    assert hasattr(mcp, "_blob_material"), "the material builder is missing"


def test_proof_standard_is_scoped_by_claim_type():
    assert "scope the demand to the claim" in TEXT, "the proof-scoping rule is absent"
    assert "historical measurement" in TEXT.lower(), (
        "the historical-measurement case is absent: those claims must be satisfied by a POINTER")
    assert "operator directive" in TEXT.lower(), (
        "the external-instruction case is absent: a quoted directive is a recorded fact")
    assert "POINT AT its record" in TEXT, "the pointer requirement is absent"


def test_strict_case_survives_the_scoping():
    """E. The whole point of the condition: behaviour still needs an executable check."""
    assert "does NOT relax" in TEXT, "the strict-case note is absent from the scoping rule"
    assert "committed, re-runnable test or script, in this range" in TEXT, (
        "behavioural proof is no longer demanded — that WOULD be a lessening of governance")
    assert "is `unverified-claim`" in TEXT, "the strict case no longer names its finding technique"


def test_sibling_rule_is_stated_and_forbids_fabrication():
    assert "judged on ITS OWN blob" in TEXT, "the sibling rule is absent"
    assert "as `fabrication`" in TEXT and "do not" in TEXT, (
        "the sibling rule must explicitly forbid a fabrication finding")
    assert "YOUR WINDOW" in TEXT, "the sibling rule must say it is a property of the window"


class _FakeRange:
    def __init__(self, blobs):
        self.blobs = dict(blobs)

    def __enter__(self):
        self._saved = (mcp._push_range_blobs, mcp._git_capture)
        mcp._push_range_blobs = lambda repo: dict(self.blobs)
        mcp._git_capture = lambda repo, *a: ""
        return self

    def __exit__(self, *exc):
        mcp._push_range_blobs, mcp._git_capture = self._saved
        return False


CTX = {"sid": "s", "author": "a", "branch": "b", "head_sha": "h", "cycle_id": 1,
       "task_id": "t", "description": "d"}


def test_material_names_the_siblings():
    with _FakeRange({"a/one.py": "1" * 40, "b/two.py": "2" * 40, "c/three.py": "3" * 40}):
        material = mcp._blob_material(Path("/tmp"), "base", "b/two.py", CTX)
    assert "b/two.py" in material and "file: b/two.py" in material, "the reviewed file must be named"
    assert "a/one.py" in material and "c/three.py" in material, (
        "the other files in the range must be named so the sibling rule can be applied")
    assert "b/two.py" not in material.split("range files")[1].split("\n")[1], (
        "the sibling list must not repeat the file under review")
    assert "SIBLING claim" in material, "the sibling instruction must reach the reviewer"


def test_material_has_no_sibling_block_when_there_are_none():
    with _FakeRange({"only/file.py": "9" * 40}):
        material = mcp._blob_material(Path("/tmp"), "base", "only/file.py", CTX)
    assert "SIBLING claim" not in material, "a lone file must not get a sibling block"
    assert "scope: ONE file of this range" in material, "the scope line must survive"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{'FAILED' if fails else 'OK'} — {fails} failure(s)")
    raise SystemExit(1 if fails else 0)
