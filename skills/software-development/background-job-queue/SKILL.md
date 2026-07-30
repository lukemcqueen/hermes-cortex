--- Full content (truncated) ---
---
title: Background Job Queue
name: background-job-queue
version: 1.0.0
description: Add durable background job processing to a FastAPI/asyncpg app using arq. Covers project layout, job function contract, DB session management, worker entrypoint, Docker Compose service, run-script command, and testing strategy.
trigger:
  - User says "add job queue", "arq", "background job", "worker", "durable task"
  - Task involves long-running async work (exports, reconciliation, batch processing)
  - Adding a new job type to an existing arq worker
role: developer-agent
---

# Background Job Queue (arq)

## Prerequisites

- FastAPI app with async SQLAlchemy + asyncpg
- Redis already in the stack
- ``arq>=0.26`` in ``pyproject.toml``

## Structure

```
apps/api/
├── app/
│   └── jobs/
│       ├── __init__.py       # JobQueue helper, pool factory, JOB_FUNCTIONS registry
│       ├── export_jobs.py    # Job functions per concern
│       └── reconciliation_jobs.py
├── arq_worker.py              # Worker entrypoint (s
... [truncated]
--- End skill ---