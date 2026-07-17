--- Full content (truncated) ---
---
name: dcf-model
description: Build institutional-quality DCF valuation models in Excel — revenue projections, FCF build, WACC, terminal value, Bear/Base/Bull scenarios, 5x5 sensitivity tables. Pairs with excel-author. Use for intrinsic-value equity analysis.
version: 1.0.0
author: Anthropic (adapted by Nous Research)
license: Apache-2.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [finance, valuation, dcf, excel, openpyxl, modeling, investment-banking]
    related_skills: [excel-author, pptx-author, comps-analysis, lbo-model, 3-statement-model]
---

## Environment

This skill assumes **headless openpyxl** — you are producing an .xlsx file on disk.
Follow the `excel-author` skill's conventions for cell coloring, formulas, named ranges, and sensitivity tables.
Recalculate before delivery: `python /path/to/excel-author/scripts/recalc.py ./out/model.xlsx`.

# DCF Model Builder

## Overview

This skill creates institutional-quality DCF models for equity valuation fol
... [truncated]
--- End skill ---