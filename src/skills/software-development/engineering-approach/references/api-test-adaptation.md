# API Test Adaptation Patterns

## Problem: API endpoint contract change breaks test state setup

When an API endpoint adds strict validation (format requirements, auth, business rules),
tests that relied on that endpoint as a state-transition mechanism break.

**Example:** `test_pause_completed_job` in `test_ingestion.py` called the upload endpoint
with a `.csv` file to get the job to "completed" status. The upload endpoint was later
hardened to accept only `.crd` files with proper CRD format parsing. The test was no
longer able to use upload as a side channel for state setup.

## Fix: Bypass the API, manipulate DB state directly

When the test's real goal is to test behavior *after* a certain state, set that state
directly in the DB instead of going through the restrictive API.

```python
from tests.conftest import engine as test_engine

def test_something(self, client: TestClient):
    # Create via API (simple creation endpoints are usually fine)
    res = client.post("/api/v1/ingestion/jobs", json={"file_name": "test.crd"})
    job_id = res.json()["job_id"]

    # Bypass restrictive endpoints — set state directly in DB
    session = Session(test_engine)
    try:
        job = session.query(IngestionJob).filter(IngestionJob.job_uuid == job_id).first()
        assert job is not None
        job.status = "completed"
        session.commit()
    finally:
        session.close()

    # Now test the behavior you care about
    res = client.post(f"/api/v1/ingestion/jobs/{job_id}/pause")
    assert res.status_code == 409
```

## When to use

- The endpoint requires specific file formats, complex payloads, or external dependencies
  (file storage, message queues) that are irrelevant to the state you need to reach.
- The test file already has the `Session(test_engine)` pattern established for DB read
  verification — using it for writes is consistent.
- The state transition you need is simple (status change, field update) and the endpoint
  cost outweighs the value of testing it again.

## When NOT to use

- The test is specifically testing the upload/pause flow end-to-end — keep the real
  endpoint call.
- The state involves complex relational setup (multiple tables, foreign keys, computed
  fields) — use seed fixtures or factory functions instead of raw SQL.
- The endpoint is simple and fast — prefer real calls to keep tests honest about what
  the API actually requires.
