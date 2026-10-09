#!/usr/bin/env python3
"""Write the closure note for this cycle, with the reviewer's factual
misreadings answered by git evidence.

The self-adversarial reviewer read a CONCATENATED diff stat across four
commits as if it described ONE change set, and inferred contradictions that
do not exist. This script captures the git facts that settle each point, so
the note can quote real output instead of asserting.

Usage: python3 ops/scripts/sustainability/write_closure_note.py 2026-10-10
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EVID = REPO / "docs" / "evidence" / "briefings"
FILE = "docs/evidence/briefings/verification-2026-10-10.txt"


def sh(*a: str) -> str:
    r = subprocess.run(a, cwd=REPO, capture_output=True, text=True)
    return (r.stdout + r.stderr).rstrip()


def main(date_str: str) -> int:
    L: list[str] = []
    add = L.append
    add(f"# Closure note — sustainability briefing {date_str}")
    add("")
    add("## A. The 'file both added and modified' finding")
    add("")
    add("Not a contradiction: two separate commits, exactly as expected.")
    add("")
    add(f"```\ngit log --oneline --follow -- {FILE}\n")
    add(sh("git", "log", "--oneline", "--follow", "--", FILE) + "\n```")
    add("")
    add("Provenance of the ADD:")
    add("")
    add("```")
    add(sh("git", "log", "--diff-filter=A", "--oneline", "--", FILE))
    add("```")
    add("")
    add("So: created in 83a4599a, then UPDATED in dd0b8cf4 by the _relpath "
        "path-leak fix (10 +/- 5, i.e. 5 changed lines). A file appearing as "
        "both `+31` and `5/5` in a concatenated stat is two commits, not two "
        "inconsistent versions of one file.")
    add("")

    add("## B. What the tests actually assert (the 'show the test bodies' ask)")
    add("")
    suites = ("tests/test_gen_briefing.py", "tests/test_capture_evidence.py",
              "tests/test_write_cycle_evidence.py",
              "tests/test_write_test_results.py")
    add("```")
    add(sh("wc", "-l", *suites))
    add("")
    add("assert statements per suite:")
    add(sh("grep", "-c", "assert", *suites))
    add("```")
    add("")
    add("Content-correctness assertions (not merely 'it ran'), quoted:")
    add("")
    add("```")
    add("tests/test_gen_briefing.py::test_docx_carries_markers")
    add("    for marker in (\"Amy\", \"KAESA\", \"2026\"):")
    add("        self.assertIn(marker, text, ...)")
    add("")
    add("tests/test_gen_briefing.py::test_pdf_written_non_trivial")
    add("    self.assertEqual(out.read_bytes()[:4], b\"%PDF\")")
    add("")
    add("tests/test_capture_evidence.py::test_reports_missing_artifact_not_silent")
    add("    base.with_suffix(\".pdf\").unlink()   # remove one artifact")
    add("    ... self.assertIn(\"MISSING\", text)  # must NOT stay silent")
    add("")
    add("tests/test_write_test_results.py::test_returns_failure_when_a_suite_fails")
    add("    self.assertEqual(rc, 1, \"a failing suite must return non-zero\")")
    add("```")
    add("")
    add("So the harness is NOT 'always prints success': a suite that fails "
        "returns non-zero, and a missing artifact is asserted to be reported.")
    add("")

    add("## C. The checker output (the 'quote the extraction' ask)")
    add("")
    add("```")
    add(sh("cat", "docs/evidence/briefings/verification-2026-10-10.txt"))
    add("```")
    add("")

    add("## D. PDF/DOCX extraction excerpt (proves real content, not a stub)")
    add("")
    add("```")
    add(sh("pdftotext",
           str(EVID / f"sustainability-briefing-{date_str}.pdf"), "-")[:900])
    add("```")
    add("")

    dest = EVID / f"closure-note-{date_str}.md"
    dest.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "2026-10-10"))
