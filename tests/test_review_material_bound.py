#!/usr/bin/env python3
"""The review material's diff bound: HEAD+TAIL, and the cut must be disclosed.

Cycle 10488's close was refused with findings claiming the daemon implementation and its
tests were missing from the material. They were not missing — the gate's diff bound was
head-only while its comment claimed head+tail, so a large implementation diff was cut
mid-line ("A turn is IN FLI..."). An adversarial reviewer reading that material correctly
reported the evidence as absent. This test pins the bound itself: the tail survives, the
omission is disclosed with true numbers, and the files in the cut are named.

Run: python3 -m pytest tests/test_review_material_bound.py -q -s
"""
import importlib.util
import logging as _logging
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_bound",
                                               REPO / "mcp-servers" / "loop-gov-mcp.py")
assert _spec and _spec.loader, "cannot load the gate module"
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

# Do not write into the production governance log (same discipline as the other gate tests).
_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)
_gate_log.propagate = False


def _diff(files: int, body_lines: int = 40) -> str:
    out = []
    for i in range(files):
        out.append(f"diff --git a/file{i}.py b/file{i}.py")
        out.append(f"--- a/file{i}.py")
        out.append(f"+++ b/file{i}.py")
        out.append(f"@@ -1,{body_lines} +1,{body_lines} @@")
        out += [f"+ added line {n} of file{i}" for n in range(body_lines)]
    return "\n".join(out) + "\n"


def test_short_diff_is_returned_unchanged():
    small = _diff(1, 3)
    assert mcp._bound_diff(small, budget=100000) == small, "a diff within budget must be untouched"
    print("  short diff passes through unchanged ✓")


def test_the_tail_survives_the_bound():
    """The actual defect: the old code kept only the head and dropped the tail."""
    big = _diff(20, 40)
    budget = 2000
    got = mcp._bound_diff(big, budget=budget)
    # The material must END inside the LAST changed file's section, so that file's tail
    # survives. (Under a per-file budget the last file keeps a proportional tail, not the
    # whole 200-char suffix it would keep under one window — pin the property, not a size.)
    last_section = big[big.rindex("diff --git a/file19.py"):]
    last_line = got.rstrip().splitlines()[-1]
    assert not last_line.startswith("...["), \
        "the material must not end on a disclosure marker — that would mean content was dropped last"
    assert last_line in last_section, \
        f"THE TAIL MUST SURVIVE — the final line must come from the last changed file; got {last_line!r}"
    # The FIRST file's section is present with body, not just a header.
    assert "diff --git a/file0.py" in got, "the first changed file's section must be present"
    assert "+ added line" in got, "the material must contain body content, not only headers"
    # control: reproduce the old behaviour and show it loses the last file entirely
    old = big[:budget] + "\n...[diff truncated]...\n"
    assert "file19.py" not in old, "control: the old single-window form loses the last files"
    print("  head+tail per file ✓ (last file's tail survives); control lost file19 entirely")


def test_the_omission_is_disclosed_with_true_numbers():
    """The notice's TOTAL must equal the sum of the per-file omissions it reports."""
    import re
    big = _diff(20, 40)
    budget = 2000
    got = mcp._bound_diff(big, budget=budget)
    assert "MATERIAL LIMIT" in got
    assert "not absent evidence" in got, \
        "the notice must say the cut is the gate's limit, not missing evidence"
    per_file = [int(n) for n in re.findall(r"(\d+) of \d+ chars omitted from its middle", got)]
    assert per_file, "each bounded file must disclose its own omission with true numbers"
    total_line = re.search(r"(\d+) of (\d+) chars were omitted in total", got)
    assert total_line, "the notice must carry a total"
    assert int(total_line.group(1)) == sum(per_file), \
        (f"the total ({total_line.group(1)}) must equal the sum of the per-file omissions "
         f"({sum(per_file)}) — a total that disagrees with its parts is a contradiction")
    assert int(total_line.group(2)) == len(big), "the denominator must be the real diff size"
    # And the parts must be TRUE: every changed file must still show some of its body.
    for path, section in mcp._split_diff_sections(big):
        stem = path.split("/")[-1].rsplit(".", 1)[0]        # "file0.py" -> "file0"
        shown_here = [l for l in got.splitlines() if l.startswith("+ added line") and f"of {stem}" in l]
        assert shown_here, f"{path} shows no body at all"
    print(f"  disclosure totals match the parts ({sum(per_file)} of {len(big)}) ✓")


def test_the_files_in_the_cut_are_named():
    big = _diff(20, 40)
    got = mcp._bound_diff(big, budget=2000)
    assert "files bounded above" in got, "the notice must name the bounded files"
    named = [f"file{i}.py" for i in range(20) if f"file{i}.py" in got]
    assert named, "at least some of the bounded files must be named"
    print(f"  bounded files are named ({len(named)} of 20) ✓")


def test_no_changed_file_is_omitted_entirely():
    """THE regression (2026-10-08): a single window over the whole diff hid WHOLE files.

    Five changed files against the 12000-char budget dropped 19509 of 29260 chars from the
    middle, and the middle files were absent in their entirety — so the reviewer correctly
    reported their content as missing from the material, and three closes were refused for
    a condition the worker could not fix. Every changed file must be represented.
    """
    big = _diff(24, 40)
    budget = 2000
    got = mcp._bound_diff(big, budget=budget)
    missing = [f"file{i}.py" for i in range(24) if f"diff --git a/file{i}.py" not in got]
    assert not missing, \
        f"every changed file must appear in the material; omitted entirely: {missing}"
    # ...and each of them must carry real content, not just its header line.
    for i in range(24):
        body = [l for l in got.splitlines() if l.startswith(f"+ added line") and f"file{i}" in l]
        assert body, f"file{i}.py appears with a header but no body — a header is not the change"
    # CONTROL: the old one-window form drops middle files entirely.
    head = budget * 2 // 3
    tail = budget - head
    old = big[:head] + "\n...[MATERIAL LIMIT]...\n" + big[len(big) - tail:]
    old_missing = [f"file{i}.py" for i in range(24) if f"diff --git a/file{i}.py" not in old]
    assert old_missing, "control: the old single-window form must lose middle files"
    print(f"  all 24 files present with body ✓ (control: the old window lost {len(old_missing)})")


def test_the_gate_actually_uses_the_helper():
    """Regression guard: a bare slice would silently reintroduce the head-only bug."""
    src = (REPO / "mcp-servers" / "loop-gov-mcp.py").read_text()
    assert "_bound_diff(diff_text)" in src, "the gate must bound the diff via _bound_diff()"
    assert "diff_text[:DIFF_CHAR_BUDGET]" not in src, \
        "a bare head-only slice is the bug this test exists to prevent"
    assert "...[diff truncated]..." not in src, "the old silent marker must be gone"
    print("  gate uses _bound_diff; no bare head-only slice remains ✓")


# ── Docs-only budget (2026-10-07) ─────────────────────────────────────────────
# For CODE a head+tail window is a workable review. For DOCS the diff IS the
# artifact, so truncation is not a smaller review — it is no review. Cycle 10838
# was a ~39KB docs range against the 12KB budget; the document under review AND
# the evidence for it were both in the omitted middle. These pin the relaxation
# and, more importantly, pin that it is COMPUTED rather than claimed.


def _docs_diff(files: int, body_lines: int = 120) -> str:
    """A docs-only diff, all `.md`, big enough to exceed the standard budget."""
    out = []
    for i in range(files):
        out.append(f"diff --git a/docs/guide{i}.md b/docs/guide{i}.md")
        out.append(f"--- a/docs/guide{i}.md")
        out.append(f"+++ b/docs/guide{i}.md")
        out.append(f"@@ -1,{body_lines} +1,{body_lines} @@")
        out += [f"+ documentation line {n} of guide{i} " + "x" * 60 for n in range(body_lines)]
    return "\n".join(out) + "\n"


def test_docs_only_range_gets_the_larger_budget():
    d = _docs_diff(4)
    assert len(d) > mcp.DIFF_CHAR_BUDGET, "fixture must exceed the standard budget"
    assert len(d) < mcp.DIFF_CHAR_BUDGET_DOCS, "fixture must fit the docs budget"
    out = mcp._bound_diff(d)
    assert "MATERIAL LIMIT" not in out, "a docs range that fits the docs budget must NOT be cut"
    assert "REVIEW MATERIAL POLICY" in out and "docs budget" in out, "the policy must be disclosed"
    print(f"  docs-only range ({len(d)} chars) not truncated, policy disclosed ✓")


def test_one_code_file_reverts_to_the_standard_budget():
    d = _docs_diff(5) + "diff --git a/ops/scripts/thing.py b/ops/scripts/thing.py\n" + "x" * 4000
    out = mcp._bound_diff(d)
    assert "MATERIAL LIMIT" in out, "one non-doc path must revert to the standard budget"
    assert "REVIEW MATERIAL POLICY" not in out, "a non-docs range must not claim the docs policy"
    print("  one .py file reverts the whole range to the standard budget ✓")


def test_always_review_path_disqualifies_even_markdown():
    d = _docs_diff(4) + ("diff --git a/ops/install/hooks/README.md b/ops/install/hooks/README.md\n"
                         + "x" * 4000)
    assert mcp._range_is_docs_only(d) is False, "an always-review path must disqualify the range"
    print("  always-review path disqualifies a .md-only range ✓")


def test_empty_diff_is_not_docs_only():
    assert mcp._range_is_docs_only("") is False, "nothing parsed must never mean docs-only"
    assert "REVIEW MATERIAL POLICY" not in mcp._bound_diff("")
    print("  empty/unparseable diff is NOT docs-only ✓")


def test_notice_states_the_limit_without_directing_the_reviewer():
    out = mcp._bound_diff(_docs_diff(20))          # forces the docs budget to truncate too
    assert "MATERIAL LIMIT" in out
    assert "read_file" not in out, "the notice must not instruct the reviewer"
    assert "split the cycle" in out, "an over-budget docs range must say what to do instead"
    print("  over-budget docs notice is neutral and says to split the cycle ✓")


def test_an_explicit_budget_is_still_honoured():
    d = _docs_diff(6)
    out = mcp._bound_diff(d, budget=1000)
    assert "MATERIAL LIMIT" in out and "1000-char budget" in out, "explicit budget wins"
    print("  explicit budget override still honoured ✓")


# ── Standalone runner ─────────────────────────────────────────────────────────
# pytest is not installed on every fleet host, which left this file unrunnable
# there and its assertions unverified. Run it directly:
#     python3 tests/test_review_material_bound.py
if __name__ == "__main__":
    import sys
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
        except Exception:
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    print()
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        sys.exit(1)
    print(f"RESULT: ALL PASS ({len(tests)} tests)")
