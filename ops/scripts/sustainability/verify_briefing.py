#!/usr/bin/env python3
"""verify_briefing — validate the daily sustainability briefing artifacts.

The content-production cron writes a briefing as .md/.docx/.pdf. This checker
turns "it looks fine" into a pass/fail every close can cite. It is the
re-runnable evidence for the review gate: a reviewer runs it against the
committed artifacts and gets the same verdict.

Usage:
    python3 ops/scripts/sustainability/verify_briefing.py 2026-10-08
    python3 ops/scripts/sustainability/verify_briefing.py 2026-10-08 --dir /path

Interface note: the individual check_* functions are imported by
tests/test_verify_briefing.py, so keep their names and (bool) return contract.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import zipfile

DEFAULT_DIR = os.path.expanduser("~/.hermes/cron/output")

REQUIRED_SECTIONS = ("1. ", "2. ", "3. ", "4. ", "For Your Radar")
MIN_URLS = 13          # >= one per factual item in the briefing
WORD_MIN, WORD_MAX = 600, 1200
MIN_FILE_BYTES = 1000
MIN_BINARY_COVERAGE = 0.80   # share of the .md's content words the binary must carry


def check_sections(text: str) -> bool:
    """All five required H2 headings present."""
    present = [m for m in REQUIRED_SECTIONS
               if re.search(rf"^## [^\n]*{re.escape(m)}", text, re.M)]
    return len(present) == len(REQUIRED_SECTIONS)


def check_sources(text: str) -> bool:
    """At least MIN_URLS 'Source:' lines, each a well-formed URL."""
    good = re.findall(r"^Source: (https?://\S+)$", text, re.M)
    malformed = re.findall(r"^Source: (?!https?://)\S+", text, re.M)
    return len(good) >= MIN_URLS and not malformed


def check_word_count(text: str) -> bool:
    """Body word count inside [WORD_MIN, WORD_MAX]."""
    return WORD_MIN <= len(text.split()) <= WORD_MAX


def check_files(directory: str, date_str: str) -> bool:
    """All three artifacts exist and are non-trivial."""
    base = os.path.join(directory, f"sustainability-briefing-{date_str}")
    for ext in (".md", ".docx", ".pdf"):
        path = base + ext
        if not os.path.exists(path) or os.path.getsize(path) < MIN_FILE_BYTES:
            return False
    return True


def _docx_text(path: str) -> str:
    return re.sub(r"<[^>]+>", "",
                  zipfile.ZipFile(path).read("word/document.xml").decode("utf-8"))


def _pdf_text(path: str) -> str:
    try:
        return subprocess.run(["pdftotext", path, "-"], capture_output=True,
                              text=True, timeout=30).stdout
    except FileNotFoundError:
        return ""


def _content_words(text: str) -> set:
    """Distinct >=5-letter words, lowercased — tolerant of PDF line wrapping."""
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]{4,}", text or "")}


def check_binary_carry_text(directory: str, date_str: str,
                            text: str | None = None) -> bool:
    """The .docx/.pdf artifacts actually carry THIS briefing's text.

    The expected tokens are derived from the delivered .md — never a fixed
    topic word. A hardcoded token ('EmpCo') made the check demand that every
    briefing discuss the EU green-claims directive, so a healthy briefing on
    any other subject failed a check whose whole contract is binary fidelity
    (measured 2026-10-23: sustainability-briefing-2026-10-22, a briefing about
    Korea's greenwashing rules, failed on the missing topic word while its
    docx/pdf carried the text). Measured coverage on the real delivered
    artifacts: docx 0.87-0.98, pdf 0.97-1.00; unrelated/empty artifacts ~0.00.
    """
    base = os.path.join(directory, f"sustainability-briefing-{date_str}")
    if text is None:
        text = open(base + ".md", encoding="utf-8").read()
    expected = _content_words(text)
    if not expected:
        return False

    def carries(sample: str) -> bool:
        return len(expected & _content_words(sample)) / len(expected) >= MIN_BINARY_COVERAGE

    return carries(_docx_text(base + ".docx")) and carries(_pdf_text(base + ".pdf"))


def main(date_str: str, directory: str) -> int:
    base = os.path.join(directory, f"sustainability-briefing-{date_str}")
    ok = True

    files_ok = check_files(directory, date_str)
    ok &= files_ok
    for ext in (".md", ".docx", ".pdf"):
        p = base + ext
        size = os.path.getsize(p) if os.path.exists(p) else -1
        print(f"[files] {os.path.basename(p):<42} size={size:<8} "
              f"{'PASS' if size >= MIN_FILE_BYTES else 'FAIL'}")

    text = open(base + ".md", encoding="utf-8").read()

    s_ok = check_sections(text); ok &= s_ok
    print(f"[sections] required headings {'PASS' if s_ok else 'FAIL'}")
    src_ok = check_sources(text); ok &= src_ok
    n = len(re.findall(r"^Source: https?://", text, re.M))
    print(f"[sources] source lines={n} (>= {MIN_URLS}) "
          f"{'PASS' if src_ok else 'FAIL'}")
    w_ok = check_word_count(text); ok &= w_ok
    print(f"[words] count={len(text.split())} "
          f"({WORD_MIN}-{WORD_MAX}) {'PASS' if w_ok else 'FAIL'}")
    b_ok = check_binary_carry_text(directory, date_str, text); ok &= b_ok
    print(f"[binary] docx+pdf carry briefing text {'PASS' if b_ok else 'FAIL'}")

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    date = args[0] if args and not args[0].startswith("--") else "2026-10-08"
    out_dir = DEFAULT_DIR
    if "--dir" in args:
        out_dir = args[args.index("--dir") + 1]
    sys.exit(main(date, out_dir))
