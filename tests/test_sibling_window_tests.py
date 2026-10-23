#!/usr/bin/env python3
"""The per-blob window carries sibling TEST IDS, not only the first N added lines.

A test file's first added lines are imports and describe-block boilerplate, so a claim proved by a
test in ANOTHER file of the range could not be verified from the window that judged it: the test id
was never shown, and the judged file was asked for evidence it cannot contain.

Boundary this file asserts:
  A. _rank_siblings puts test-shaped siblings first, so an alphabetically late spec is not pushed
     out of the bounded block, and order within each group is preserved;
  B. _collect_added_tests returns the test ids the range ADDED, each with its first assertion line;
  C. a definition whose body asserts nothing is reported with an EMPTY assertion — a name that
     proves nothing must be visible AS such, never accepted on its name alone;
  D. _format_sibling_tests renders both the id and the assertion, and says so plainly when there is
     no assertion line to show.

DEPENDENCY POINTER: these helpers live in mcp-servers/loop-gov-mcp.py and are exercised here through
the module's own exported names; this file is test-side proof of the boundary, not a copy of it.
"""
import importlib.util
import logging as _logging
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("loop_gov_sibwin", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)
_logging.getLogger("loop-governance").setLevel(_logging.CRITICAL + 1)


# ── A. ranking ───────────────────────────────────────────────────────────────
def test_test_shaped_siblings_come_first():
    ranked = mcp._rank_siblings(["app/services/x.rb", "app/services/y.rb", "spec/services/x_spec.rb"])
    assert ranked[0] == "spec/services/x_spec.rb"


def test_rank_preserves_order_within_each_group():
    # The caller hands over an already-sorted list, so ranking must be STABLE inside each group:
    # members keep their incoming order and only the groups move.
    ranked = mcp._rank_siblings(["app/b.rb", "app/a.rb", "tests/z.py", "tests/y.py"])
    assert ranked == ["tests/z.py", "tests/y.py", "app/b.rb", "app/a.rb"]


def test_rank_is_stable_for_a_single_group():
    assert mcp._rank_siblings(["a.py", "b.py"]) == ["a.py", "b.py"]


def test_rank_of_empty_is_empty():
    assert mcp._rank_siblings([]) == []


# ── B. collection ────────────────────────────────────────────────────────────
def test_python_definition_with_assertion():
    tests = mcp._collect_added_tests(["+def test_alpha():", "+    assert compute() == 1"])
    assert len(tests) == 1
    name, assertion = tests[0]
    assert name == "test_alpha"
    assert "assert compute() == 1" in assertion


def test_ruby_example_with_expectation():
    tests = mcp._collect_added_tests(['+  it "reissues no number" do', "+    expect(seq).to eq(7)"])
    assert len(tests) == 1
    name, assertion = tests[0]
    assert name == "reissues no number"
    assert "expect(seq).to eq(7)" in assertion


def test_two_definitions_are_reported_separately():
    tests = mcp._collect_added_tests([
        "+def test_one():", "+    assert one()",
        "+def test_two():", "+    assert two()",
    ])
    assert [n for n, _ in tests] == ["test_one", "test_two"]
    assert "assert two()" in tests[1][1]


def test_no_definitions_yields_nothing():
    assert mcp._collect_added_tests(["+import os", "+x = 1"]) == []


def test_plain_comparison_is_not_an_assertion():
    # A bare `==` is not an assertion. A comparison inside a body must not be reported as one, or
    # the window shows a line that proves nothing while looking like proof.
    tests = mcp._collect_added_tests(["+def test_flag():", "+    flag = a == b"])
    assert len(tests) == 1
    assert tests[0][1] == ""


def test_empty_input_yields_nothing():
    assert mcp._collect_added_tests([]) == []


# ── C. a name that proves nothing is visible as such ─────────────────────────
def test_definition_without_assertion_reports_empty_assertion():
    tests = mcp._collect_added_tests(["+def test_nothing():", "+    pass"])
    assert len(tests) == 1
    assert tests[0][0] == "test_nothing"
    assert tests[0][1] == ""


def test_assertion_must_belong_to_its_own_definition():
    tests = mcp._collect_added_tests([
        "+def test_first():", "+    assert first()",
        "+def test_second():", "+    pass",
    ])
    assert tests[1][0] == "test_second"
    assert tests[1][1] == "", "an assertion from an earlier definition must not be borrowed"


# ── D. rendering ─────────────────────────────────────────────────────────────
def test_block_names_the_id_and_the_assertion():
    block = mcp._format_sibling_tests("spec/x_spec.rb", [("reissues no number", "expect(seq).to eq(7)")])
    assert "spec/x_spec.rb::reissues no number" in block
    assert "expect(seq).to eq(7)" in block


def test_block_says_when_there_is_no_assertion_line():
    block = mcp._format_sibling_tests("tests/x.py", [("test_nothing", "")])
    assert "tests/x.py::test_nothing" in block
    assert "no assertion line" in block.lower()
