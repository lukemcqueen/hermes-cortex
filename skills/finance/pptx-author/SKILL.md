--- Full content (truncated) ---
---
name: pptx-author
description: Build PowerPoint decks headless with python-pptx. Pairs with excel-author for model-backed decks where every number traces to a workbook cell. Use for pitch decks, IC memos, earnings notes.
version: 1.0.0
author: Anthropic (adapted by Nous Research)
license: Apache-2.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [powerpoint, pptx, python-pptx, presentation, finance]
    related_skills: [excel-author, powerpoint]
---

# pptx-author

Produce a .pptx file on disk using `python-pptx`. Use when you need to deliver a deck as a file artifact, not drive a live PowerPoint session.

Adapted from Anthropic's `pptx-author` and `pitch-deck` skills in [anthropics/financial-services](https://github.com/anthropics/financial-services). The MCP / Office-JS branches of the originals are dropped — this assumes headless Python.

For the broader, already-shipped PowerPoint authoring skill (slides, speaker notes, embeds, media), see the built-in `powerp
... [truncated]
--- End skill ---