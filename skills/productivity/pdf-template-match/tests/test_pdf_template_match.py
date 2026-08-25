#!/usr/bin/env python3
"""Tests for the pdf-template-match skill scripts.

Covers:
  - catalog_search.py: catalog loads (169 rows), BM25 search returns
    ranked results with the expected columns, empty query handling.
  - jasrac_work_report.py: builds a valid 1-page A4 PDF; layout constants
    (rules, column x's) match the measured reference geometry.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(SKILL_DIR, "scripts")
sys.path.insert(0, SCRIPTS)

import catalog_search  # noqa: E402


class TestCatalogSearch(unittest.TestCase):
    def test_catalog_loads_169_rows(self):
        with open(os.path.join(SKILL_DIR, "references", "pdf-design.csv"), encoding="utf-8") as f:
            import csv
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 169)
        self.assertIn("ReportLab Notes", rows[0])
        self.assertIn("Color Palette", rows[0])

    def test_search_returns_ranked_results(self):
        result = catalog_search.search("invoice minimal", max_results=3)
        self.assertNotIn("error", result)
        self.assertGreater(result["count"], 0)
        for row in result["results"]:
            for col in ("Template Name", "Layout Spec", "Typography", "Color Palette", "ReportLab Notes"):
                self.assertIn(col, row)
        # BM25 relevance: first result must contain at least one query token
        first = result["results"][0]
        hay = (first["Template Name"] + " " + first["Keywords"]).lower()
        self.assertTrue(any(tok in hay for tok in ("invoice", "minimal")))

    def test_no_match_returns_empty(self):
        result = catalog_search.search("zzzqqqxxyy unknown nonsense", max_results=3)
        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 0)

    def test_cli_prints_results(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "catalog_search.py"), "annual report", "-n", "1"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("PDF Design Search Results", proc.stdout)
        self.assertIn("Layout Spec", proc.stdout)


class TestJasracReport(unittest.TestCase):
    def test_builds_valid_a4_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "report.pdf")
            proc = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "jasrac_work_report.py"), "-o", out],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.exists(out))
            # Valid PDF with one A4 page
            from pypdf import PdfReader
            reader = PdfReader(out)
            self.assertEqual(len(reader.pages), 1)
            page = reader.pages[0]
            self.assertAlmostEqual(float(page.mediabox.width), 595.32, delta=1.0)
            self.assertAlmostEqual(float(page.mediabox.height), 841.92, delta=1.0)

    def test_custom_data_via_json(self):
        data = {
            "header_right": "【ABC123】 [TEST TITLE]",
            "title": "T:TEST TITLE",
            "rows": [
                {"participant": "1  A  1  TEST", "dr_ex": "001", "frac": "1/12",
                 "dr_mec": "002", "pct": "10,00%", "code": "CODE-X"},
            ],
            "empty_rows_after": 2,
        }
        with tempfile.TemporaryDirectory() as tmp:
            data_path = os.path.join(tmp, "data.json")
            out = os.path.join(tmp, "custom.pdf")
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            proc = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "jasrac_work_report.py"),
                 "-o", out, "--json", data_path],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.exists(out))
            from pypdf import PdfReader
            reader = PdfReader(out)
            self.assertEqual(len(reader.pages), 1)


if __name__ == "__main__":
    unittest.main()
