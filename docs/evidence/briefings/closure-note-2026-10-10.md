# Closure note — sustainability briefing 2026-10-10

## A. The 'file both added and modified' finding

Not a contradiction: two separate commits, exactly as expected.

```
git log --oneline --follow -- docs/evidence/briefings/verification-2026-10-10.txt

dd0b8cf4 chore(sustainability): register briefing scripts + index the evidence
83a4599a evidence(sustainability): briefing 2026-10-10 + re-runnable checker harness
```

Provenance of the ADD:

```
83a4599a evidence(sustainability): briefing 2026-10-10 + re-runnable checker harness
```

So: created in 83a4599a, then UPDATED in dd0b8cf4 by the _relpath path-leak fix (10 +/- 5, i.e. 5 changed lines). A file appearing as both `+31` and `5/5` in a concatenated stat is two commits, not two inconsistent versions of one file.

## B. What the tests actually assert (the 'show the test bodies' ask)

```
  122 tests/test_gen_briefing.py
  107 tests/test_capture_evidence.py
   86 tests/test_write_cycle_evidence.py
   72 tests/test_write_test_results.py
  387 total

assert statements per suite:
tests/test_gen_briefing.py:17
tests/test_capture_evidence.py:13
tests/test_write_cycle_evidence.py:11
tests/test_write_test_results.py:11
```

Content-correctness assertions (not merely 'it ran'), quoted:

```
tests/test_gen_briefing.py::test_docx_carries_markers
    for marker in ("Amy", "KAESA", "2026"):
        self.assertIn(marker, text, ...)

tests/test_gen_briefing.py::test_pdf_written_non_trivial
    self.assertEqual(out.read_bytes()[:4], b"%PDF")

tests/test_capture_evidence.py::test_reports_missing_artifact_not_silent
    base.with_suffix(".pdf").unlink()   # remove one artifact
    ... self.assertIn("MISSING", text)  # must NOT stay silent

tests/test_write_test_results.py::test_returns_failure_when_a_suite_fails
    self.assertEqual(rc, 1, "a failing suite must return non-zero")
```

So the harness is NOT 'always prints success': a suite that fails returns non-zero, and a missing artifact is asserted to be reported.

## C. The checker output (the 'quote the extraction' ask)

```
=== evidence: sustainability briefing 2026-10-10 ===
generated: 2026-10-09T21:14:44.634283+00:00

--- command: ~/.hermes/cron/output/.venv-brief/bin/python ~/hermes-cortex/ops/scripts/sustainability/verify_briefing.py 2026-10-10
[files] sustainability-briefing-2026-10-10.md      size=9591     PASS
[files] sustainability-briefing-2026-10-10.docx    size=41293    PASS
[files] sustainability-briefing-2026-10-10.pdf     size=10635    PASS
[sections] required headings PASS
[sources] source lines=22 (>= 13) PASS
[words] count=1193 (600-1200) PASS
[binary] docx+pdf carry briefing text PASS

RESULT: ALL PASS
checker_exit=0

--- artifact listing + sha256
     9591  32b82e25843ebc49125f15e7d3998ee3c0fdc9f00470399f8fd223455e3f2ac7  ~/.hermes/cron/output/sustainability-briefing-2026-10-10.md
    41293  d024989fa07a343a9cc51a6472825a8b186128228b7ed53e7e2563267fbf58f5  ~/.hermes/cron/output/sustainability-briefing-2026-10-10.docx
    10635  b1bdf7949e578c8f9c2351d8ae0709d690b841b6ac5b5d5910ca8276c9042f6f  ~/.hermes/cron/output/sustainability-briefing-2026-10-10.pdf

--- distinct source URLs in md: 18
--- Source: lines: 22
--- word count: 1193

--- pdf text extraction spot-check (first 6 lines)
Sustainable Materials & Market Intelligence Briefing
Saturday, 10 October 2026 — prepared for Amy, KAESA

1. Headline: The PFAS Deadline Is Today — and Korea's Sustainable Leather
Numbers Just Got Interesting
Two things land on the same day, and they point the same direction.
```

## D. PDF/DOCX extraction excerpt (proves real content, not a stub)

```
Sustainable Materials & Market Intelligence Briefing
Saturday, 10 October 2026 — prepared for Amy, KAESA

1. Headline: The PFAS Deadline Is Today — and Korea's Sustainable Leather
Numbers Just Got Interesting
Two things land on the same day, and they point the same direction.
Regulation (EU) 2024/2462 — the PFHxA restriction under REACH — applies from 10 October 2026 to textiles,
leather, furs and hides used in clothing and accessories, plus all footwear for the general public. The limits: 25
ppb for PFHxA and its salts, 1,000 ppb for related substances, measured in homogeneous material. It widens on
10 October 2027 beyond apparel and accessories. The one genuine buffer: it does not apply to products placed
on the market before the application date. That protects stock already sold in. It does not protect anything you are
about to order.
Source: https://www.bdlaw.com/publications/new-eu-
```

