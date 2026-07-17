--- Full content (truncated) ---
---
name: batch-job-optimization
description: "Systematically analyze and optimize database-bound batch processing jobs (imports, exports, ETL, bulk updates) in Rails and similar frameworks."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [performance, optimization, batch, database, profiling, queries]
    related_skills: [systematic-debugging, project-map, server-hardening]
---

# Batch Job Optimization

## When to Use

- User reports a job is "too slow" (import, export, migration, ETL, bulk update)
- User asks "why is this import taking hours?"
- User asks "how can I make this job faster?"
- User asks you to analyze slow queries in a batch context
- A job processes large datasets row-by-row or in small batches

This is for BATCH jobs, not web request latency. Web performance profiling uses different tools (rack-mini-profiler, scout, skylight).

## The Methodology

A batch job's performance is determined by the number of queries per 
... [truncated]
--- End skill ---