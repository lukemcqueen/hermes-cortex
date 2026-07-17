--- Full content (truncated) ---
---
name: comps-analysis
description: Build comparable company analysis in Excel — operating metrics, valuation multiples, statistical benchmarking vs peer sets. Pairs with excel-author. Use for public-company valuation, IPO pricing, sector benchmarking, or outlier detection.
version: 1.0.0
author: Anthropic (adapted by Nous Research)
license: Apache-2.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [finance, valuation, comps, excel, openpyxl, modeling, investment-banking]
    related_skills: [excel-author, pptx-author, dcf-model, lbo-model]
---

## Environment

This skill assumes **headless openpyxl** — you are producing an .xlsx file on disk.
Follow the `excel-author` skill's conventions for cell coloring, formulas, named ranges, and sensitivity tables.
Recalculate before delivery: `python /path/to/excel-author/scripts/recalc.py ./out/model.xlsx`.

# Comparable Company Analysis

## ⚠️ CRITICAL: Data Source Priority (READ FIRST)

**ALWAYS follow this data source hie
... [truncated]
--- End skill ---