--- Full content (truncated) ---
---
name: 3-statement-model
description: Build fully-integrated 3-statement models (IS, BS, CF) in Excel with working capital schedules, D&A roll-forwards, debt schedule, and the plugs that make cash and retained earnings tie. Pairs with excel-author.
version: 1.0.0
author: Anthropic (adapted by Nous Research)
license: Apache-2.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [finance, three-statement, income-statement, balance-sheet, cash-flow, excel, openpyxl, modeling]
    related_skills: [excel-author, pptx-author, dcf-model, lbo-model]
---

## Environment

This skill assumes **headless openpyxl** — you are producing an .xlsx file on disk.
Follow the `excel-author` skill's conventions for cell coloring, formulas, named ranges, and sensitivity tables.
Recalculate before delivery: `python /path/to/excel-author/scripts/recalc.py ./out/model.xlsx`.

# 3-Statement Financial Model Template Completion

Complete and populate integrated financial model templates with prope
... [truncated]
--- End skill ---