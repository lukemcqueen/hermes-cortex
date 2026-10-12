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


# ── Per-file floor + evidence-as-documentation (2026-10-12) ───────────────────
# Cycle 12307 exposed a shape the per-file allocation could not serve: ~12 changed
# files against the STANDARD 12000 budget because one of them was `docs/evidence/*.sh`
# (a run transcript, not code), and the budget is applied to each file's DIFF text —
# headers, `+` prefixes and context included. A 244-BYTE evidence file still produced
# ~1118 chars of diff, so the reviewer saw "318 of 1118 omitted" no matter how small
# the worker made the file. Six rounds of findings were produced by that, and every one
# was unfixable from the worker's side: making the file smaller could not help.
# These pin the two halves of the fix: evidence paths count as documentation for the
# budget predicate, and every file gets a FLOOR before the equal share so a small
# artifact is shown WHOLE.


def _evidence_diff_sh(files: int = 3) -> str:
    """A run-evidence range: docs + `.sh`/`.json` transcripts under docs/evidence/."""
    out = []
    for i in range(files):
        out.append(f"diff --git a/docs/evidence/run{i}.sh b/docs/evidence/run{i}.sh")
        out.append(f"--- a/docs/evidence/run{i}.sh")
        out.append(f"+++ b/docs/evidence/run{i}.sh")
        out.append("@@ -0,0 +1,40 @@")
        out += [f"+ echo line {n} of run{i}" for n in range(40)]
    out.append("diff --git a/docs/evidence/capture.json b/docs/evidence/capture.json")
    out.append("--- a/docs/evidence/capture.json")
    out.append("+++ b/docs/evidence/capture.json")
    out.append("@@ -0,0 +1,5 @@")
    out += ['+ {"rc": 0, "verdict": "PASS"}']
    return "\n".join(out) + "\n"


def test_evidence_paths_count_as_documentation():
    """A transcript under docs/evidence/ is the artifact under review, not code.

    Same rationale as the docs budget: for an artifact, a truncated diff is not a
    smaller review — it is no review. Suffix alone must not decide it.
    """
    d = _evidence_diff_sh()
    assert mcp._range_is_docs_only(d) is True, \
        "docs/evidence/** is documentation whatever its suffix — a .sh transcript is a run artifact"
    # ...but code is still code, wherever it lives.
    d2 = d + "diff --git a/ops/scripts/thing.py b/ops/scripts/thing.py\n" + "x" * 100
    assert mcp._range_is_docs_only(d2) is False, "one real code path must revert the budget"
    print("  docs/evidence/** (.sh, .json) classified as documentation; a code path reverts it ✓")


def test_every_file_under_the_floor_is_shown_whole():
    """The 12307 defect: a tiny artifact was still cut, because the share was budget//n.

    Measured in that cycle: a 244-BYTE transcript produced 1118 chars of diff text
    (headers + `+` prefixes + context), against a share of 12000//12 ~ 1000 — so it came
    back "318 of 1118 omitted" and no amount of shrinking the file could help.
    """
    big = _diff(12, 120)                    # 12 files ABOVE the floor (~2.8KB of diff each)
    body = [f"+evidence line {n} {'.' * 60}" for n in range(16)]   # ~1.1KB artifact
    tiny = ("diff --git a/docs/evidence/tiny.txt b/docs/evidence/tiny.txt\n"
            "--- a/docs/evidence/tiny.txt\n"
            "+++ b/docs/evidence/tiny.txt\n"
            "@@ -0,0 +1,16 @@\n" + "\n".join(body) + "\n"
            "+ALL CLAIMS VERIFIED (0 failures)\n"
            "+sha256 79a6afcd8ac1\n")
    assert len(tiny) < mcp.REVIEW_MATERIAL_PER_FILE_FLOOR, "fixture: the artifact is UNDER the floor"
    assert len(tiny) > mcp.DIFF_CHAR_BUDGET // 13, \
        "the fixture must reproduce the real defect: the artifact's diff exceeds its equal share"
    got = mcp._bound_diff(big + tiny, budget=mcp.DIFF_CHAR_BUDGET)
    assert "+ALL CLAIMS VERIFIED (0 failures)" in got, \
        "a file under the per-file floor must be shown WHOLE — shrinking it further cannot help"
    assert "+sha256 79a6afcd8ac1" in got, "its last line must survive too"
    assert "+evidence line 0" in got, "its first body line must survive too"
    print(f"  under-floor artifact shown whole with 13 changed files "
          f"(floor={getattr(mcp, 'REVIEW_MATERIAL_PER_FILE_FLOOR', '?')}) ✓")


def test_the_floor_never_exceeds_the_budget():
    """A floor is an allocation preference, never a licence to exceed the budget.

    The per-file disclosure markers are overhead, so the bound is budget + a proportionate
    per-file allowance — what must never happen is unbounded growth.
    """
    d = _diff(60, 40)
    budget = 3000
    got = mcp._bound_diff(d, budget=budget)
    assert "MATERIAL LIMIT" in got, "60 files against 3000 chars must still be bounded"
    assert len(got) < budget + 150 * 60, \
        f"the material must stay proportionate to its budget; got {len(got)} for budget {budget}"
    for i in range(60):
        assert f"diff --git a/file{i}.py" in got, f"file{i} must still be represented"
    print(f"  floor respects the total budget (60 files / {budget} chars -> {len(got)} chars) ✓")


def test_the_largest_file_is_never_left_with_nothing():
    """2026-10-12 follow-up: the first floor-first cut could spend the budget on small
    files and give the largest file (always-review code under review) a 1-char sliver —
    a reviewer read a 6526-char diff as '6526 of 6526 chars omitted' and could not judge
    the code. The allocation reserves a whole REVIEW_MATERIAL_MIN_SLICE per file first.
    """
    import re
    small = [
        f"diff --git a/docs/evidence/e{i}.txt b/docs/evidence/e{i}.txt\n"
        f"--- a/docs/evidence/e{i}.txt\n+++ b/docs/evidence/e{i}.txt\n@@ -0,0 +1,40 @@\n"
        + "".join(f"+ line {k}\n" for k in range(40))
        for i in range(20)]
    big = ("diff --git a/mcp-servers/loop-gov-mcp.py b/mcp-servers/loop-gov-mcp.py\n"
           "--- a/mcp-servers/loop-gov-mcp.py\n+++ b/mcp-servers/loop-gov-mcp.py\n@@ -0,0 +1,400 @@\n"
           + "".join(f"+ def fn_{k}(): return {k}\n" for k in range(400)))
    d = "\n".join(small + [big]) + "\n"
    assert len(big) > mcp.REVIEW_MATERIAL_PER_FILE_FLOOR, \
        "fixture: the biggest file must be above the floor, so this stresses the reserve"
    got = mcp._bound_diff(d, budget=12000)
    assert "loop-gov-mcp.py" in got, "the largest (always-review) file must appear in the material"
    assert "fn_" in got, "it must carry real body, not just its header"
    # its per-file omission (if any) must leave at least a slice, not everything
    m = re.search(r"bounded: (\d+) of " + str(len(big)) + r" chars omitted", got)
    if m:
        assert int(m.group(1)) < len(big), "a fully-omitted largest file is the bug this test exists to prevent"
        print(f"  largest file gets a slice ({int(m.group(1))} of {len(big)} omitted) ✓")
    else:
        print("  largest file shown whole ✓")


def test_evidence_files_are_shown_whole_outside_the_budget():
    """Item 2 (2026-10-12): a worker's own evidence must not consume the window.

    Cycles 12307/12324: the evidence files ate the budget until a 6526-char code diff
    reviewed as '6526 of 6526 chars omitted'. Artifacts under docs/evidence/ are now shown
    whole and excluded from the split; the budget belongs to the code under review.
    """
    ev = "".join(
        f"diff --git a/docs/evidence/e{i}.txt b/docs/evidence/e{i}.txt\n"
        f"--- a/docs/evidence/e{i}.txt\n+++ b/docs/evidence/e{i}.txt\n@@ -0,0 +1,200 @@\n"
        + "".join(f"+ evidence line {k} of file {i}\n" for k in range(200)) for i in range(4))
    code = ("diff --git a/ops/scripts/thing.py b/ops/scripts/thing.py\n"
            "--- a/ops/scripts/thing.py\n+++ b/ops/scripts/thing.py\n@@ -0,0 +1,200 @@\n"
            + "".join(f"+ code_{k} = {k}\n" for k in range(200)))
    assert len(ev + code) > mcp.DIFF_CHAR_BUDGET, "fixture must exceed the standard budget to exercise the bound"
    got = mcp._bound_diff(ev + code, budget=mcp.DIFF_CHAR_BUDGET)
    assert "EVIDENCE SHOWN WHOLE" in got, "the material must say evidence is not counted against the budget"
    for i in range(4):
        assert f"+ evidence line 199 of file {i}" in got, f"evidence file {i} must be shown WHOLE (last line)"
    assert "code_0 = 0" in got, "the code under review must still show its body"
    print("  evidence shown whole; the budget is spent on the code under review ✓")


def test_material_limit_findings_do_not_block():
    """Item 6 (2026-10-12): a window complaint is not a change defect.

    The reviewer itself called these 'a gate-transport artifact, not a worker fault' and
    still blocked. Narrow: only findings that quote the gate's own limit markers AND ask
    about SEEING the content; fabrication claims always block.
    """
    import json as _json
    win = _json.dumps([{
        "finding_id": "ADV-X-1", "severity": "high", "technique": "unverified-claim",
        "target": "docs/evidence/run.txt",
        "evidence": "the file is bounded: 6000 of 9000 chars omitted from its middle",
        "recommendation": "commit the full unbounded output so the pass line is visible",
    }])
    blocking, annotating = mcp._blocking_findings(win)
    assert not blocking, "a material-window finding must not block"
    assert annotating and annotating[0].get("severity_downgraded"), "the downgrade must be recorded"

    fab = _json.dumps([{
        "finding_id": "ADV-X-2", "severity": "high", "technique": "fabrication",
        "target": "docs/evidence/run.txt",
        "evidence": "bounded: 6000 of 9000 chars omitted",
        "recommendation": "commit the full output so the line is visible",
    }])
    blocking, _ = mcp._blocking_findings(fab)
    assert blocking, "a fabrication claim must still block, whatever it quotes"

    real = _json.dumps([{
        "finding_id": "ADV-X-3", "severity": "high", "technique": "swallowed-error",
        "target": "ops/scripts/make-evidence.sh",
        "evidence": "exit 0 at end of file",
        "recommendation": "propagate the wrapped command's exit status instead of swallowing it",
    }])
    blocking, _ = mcp._blocking_findings(real)
    assert blocking, "a behavioural finding must still block"
    print("  window-only findings downgrade (recorded); fabrication and behaviour still block ✓")


def test_replayed_findings_have_quotes_stripped():
    """Item 1 (2026-10-12): a stale quote must not re-anchor a corrected note."""
    import json as _json
    payload = _json.dumps([{
        "finding_id": "ADV-Y-1", "severity": "medium",
        "evidence": "worker's note: \"this commit carries the mode change for two scripts\"",
        "recommendation": "reconcile the self-report with the diff",
    }])
    out = mcp._replay_safe_findings(payload)
    assert "this commit carries the mode change for two scripts" not in out, \
        "a quoted fragment from a superseded note must not be replayed"
    assert "[quote stripped]" in out, "the strip must be visible in what is replayed"
    assert "reconcile the self-report" in out, "the finding itself must survive"
    print("  replay strips quoted fragments; the finding's substance survives ✓")


def test_deployed_gate_behaves_as_this_file_says():
    """The DEPLOYED gate (what actually reviews closes) bounds evidence the same way.

    Without this, a grep for the constant would prove the deployed file contains the name
    but not that the FUNCTION behaves as these tests claim. It imports the deployed module
    and asserts the three load-bearing behaviours. On a host with no deployed gate (fresh
    checkout, no cortex install) it declares SKIP instead of failing — the repo tests must
    pass anywhere.
    """
    import importlib.util
    cand = REPO.parent / ".hermes-cortex" / "tools" / "loop-governance" / "loop-gov-mcp.py"
    if not cand.is_file():
        print("  SKIP — no deployed gate on this host (expected on a fresh checkout)")
        return
    spec = importlib.util.spec_from_file_location("loop_gov_mcp_deployed", cand)
    assert spec and spec.loader, "cannot load the deployed gate module"
    depm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(depm)

    ev = ("diff --git a/docs/evidence/run.sh b/docs/evidence/run.sh\n"
          "--- a/docs/evidence/run.sh\n+++ b/docs/evidence/run.sh\n@@ -0,0 +1,40 @@\n"
          + "".join(f"+ echo line {n}\n" for n in range(40)))
    assert depm._range_is_docs_only(ev) is True, "deployed predicate must treat docs/evidence/*.sh as docs"
    assert depm.DIFF_CHAR_BUDGET_DOCS > depm.DIFF_CHAR_BUDGET, "docs budget must exceed the standard one"

    big = "".join(
        f"diff --git a/file{i}.py b/file{i}.py\n--- a/file{i}.py\n+++ b/file{i}.py\n@@ -0,0 +1,120 @@\n"
        + "".join(f"+ line {n}\n" for n in range(120)) for i in range(12))
    tiny = ("diff --git a/docs/evidence/tiny.txt b/docs/evidence/tiny.txt\n"
            "--- a/docs/evidence/tiny.txt\n+++ b/docs/evidence/tiny.txt\n@@ -0,0 +1,3 @@\n"
            "+rc=0\n+ALL CLAIMS VERIFIED (0 failures)\n+sha256 79a6afcd8ac1\n")
    got = depm._bound_diff(big + tiny, budget=depm.DIFF_CHAR_BUDGET)
    assert "sha256 79a6afcd8ac1" in got, "the DEPLOYED bounder must show the under-floor artifact whole"
    assert "ALL CLAIMS VERIFIED" in got, "the DEPLOYED bounder must show its whole body"
    print(f"  deployed gate behaves as this file says "
          f"(docs budget {depm.DIFF_CHAR_BUDGET_DOCS} > {depm.DIFF_CHAR_BUDGET}, floor {depm.REVIEW_MATERIAL_PER_FILE_FLOOR}) ✓")


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
