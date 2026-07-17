--- Full content (truncated) ---
---
name: rails-data-pipeline-debugging
description: "Debugging data transformation bugs in legacy Rails apps — tracing heuristic text-splitting, internationalisation helpers, and CPLEX/CSV import pipelines."
version: 1.2.0
author: Titus
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [rails, debugging, data-pipeline, legacy, text-processing, heuristics]
    related_skills: [systematic-debugging, change-test-loop, codebase-design]
---

# Rails Data Pipeline Debugging

## Overview

Legacy Rails apps (especially music copyright / royalty systems with Korean/English i18n) rely heavily on heuristic-based helper methods to split text containing parentheses into language pairs. These heuristics silently corrupt data when a parenthetical suffix (e.g., `(INST.)`, `(MR)`, `(LIVE)`) is mistaken for a language translation.

This skill documents the pattern for tracing, diagnosing, and fixing these bugs.

## When to Use

- Song titles or artist names end up with missing suffix
... [truncated]
--- End skill ---