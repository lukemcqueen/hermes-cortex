---
title: Cron Job → Fetch API → Save Results
description: Scheduled script that fetches an external API, processes the response, stores results in a database, handles rate limiting, retries on failure, logs results, and triggers monitoring alerts on failure.
language: python
tags: [glue-code, cron, api, etl, automation]
---

# Cron Job → Fetch API → Save Results

## Overview

A robust scheduled ETL (Extract-Transform-Load) script that: fetches data from an external API, processes and transforms the response, stores results in PostgreSQL, handles rate limits with exponential backoff, retries transient failures, logs every run, and alerts when things go wrong.

---

## Database Schema

```sql
-- 0001_etl_runs.sql
CREATE TABLE etl_runs (
    id              BIGSERIAL PRIMARY KEY,
    job_name        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'success', 'failed')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    records_fetched INT DEFAULT 0,
    records_stored  INT DEFAULT 0,
    error_message   TEXT,
    duration_ms     INT
);

CREATE INDEX idx_etl_runs_job ON etl_runs(job_name, started_at DESC);

-- 0002_weather_data.sql (example output table)
CREATE TABLE weather_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    city            TEXT NOT NULL,
    temperature_c   NUMERIC(5, 2),
    humidity        INT,
    wind_speed_ms   NUMERIC(5, 2),
    description     TEXT,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    etl_run_id      BIGINT REFERENCES etl_runs(id)
);

CREATE INDEX idx_weather_city_fetched ON weather_snapshots(city, fetched_at DESC);
```

---

## The ETL Script

```python
# etl/fetch_weather.py
"""
Scheduled ETL script: fetch weather data from OpenWeatherMap API,
store in PostgreSQL, with rate limiting, retries, and monitoring.

Run via cron:
    */15 * * * * /usr/bin/python3 /path/to/etl/fetch_weather.py >> /var/log/etl/weather.log 2>&1
"""

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
import asyncpg

# --- Configuration ---
API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
API_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
CITIES = ["London", "Tokyo", "New York", "Paris", "Sydney", "Berlin", "Toronto", "Mumbai"]

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/etldb")

# Rate limiting
MAX_RETRIES = 3
BASE_DELAY = 2.0  # seconds
MAX_CONCURRENT = 3  # API rate limit guard

# Monitoring (Healthchecks.io or similar)
HEALTHCHECKS_URL = os.getenv("HEALTHCHECKS_URL", "")  # e.g. https://hc-ping.com/<uuid>

# Logging
LOG_FILE = os.getenv("ETL_LOG_FILE", "/var/log/etl/weather.log")


# --- Logging ---

def log(msg: str, level: str = "INFO") -> None:
    """Simple structured logging to stdout (captured by cron)."""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"[{timestamp}] [{level}] {msg}", flush=True)


# --- Database ---

async def get_db() -> asyncpg.Pool:
    """Create or return the database connection pool."""
    return await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=1,
        max_size=5,
    )


async def create_etl_run(pool: asyncpg.Pool, job_name: str) -> int:
    """Record the start of an ETL run."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO etl_runs (job_name, status) VALUES ($1, 'running') RETURNING id",
            job_name,
        )
        return row["id"]


async def complete_etl_run(
    pool: asyncpg.Pool,
    run_id: int,
    status: str,
    records_fetched: int = 0,
    records_stored: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """Record the completion of an ETL run."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE etl_runs
            SET status = $2,
                finished_at = NOW(),
                records_fetched = $3,
                records_stored = $4,
                error_message = $5,
                duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at))::INT * 1000
            WHERE id = $1
            """,
            run_id, status, records_fetched, records_stored, error_message,
        )


async def store_weather_data(
    pool: asyncpg.Pool,
    etl_run_id: int,
    city: str,
    weather: dict,
) -> None:
    """Store a weather snapshot into the database."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO weather_snapshots
                (city, temperature_c, humidity, wind_speed_ms, description, etl_run_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            city,
            weather.get("temperature_c"),
            weather.get("humidity"),
            weather.get("wind_speed_ms"),
            weather.get("description"),
            etl_run_id,
        )


# --- API Fetching with Retry + Rate Limiting ---

async def fetch_city_weather(
    client: httpx.AsyncClient,
    city: str,
    semaphore: asyncio.Semaphore,
) -> Optional[dict]:
    """
    Fetch weather for a single city with retry and rate limiting.
    Returns parsed weather dict or None on failure.
    """
    async with semaphore:  # limits concurrent API calls
        params = {
            "q": city,
            "appid": API_KEY,
            "units": "metric",  # Celsius
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                log(f"Fetching weather for {city} (attempt {attempt}/{MAX_RETRIES})")
                resp = await client.get(API_BASE_URL, params=params, timeout=15.0)

                # --- Handle rate limiting (HTTP 429) ---
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", str(BASE_DELAY * attempt)))
                    log(f"Rate limited on {city}. Waiting {retry_after}s", "WARN")
                    await asyncio.sleep(retry_after)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # Transform raw API response to our schema
                return {
                    "city": city,
                    "temperature_c": data["main"]["temp"],
                    "humidity": data["main"]["humidity"],
                    "wind_speed_ms": data["wind"]["speed"],
                    "description": data["weather"][0]["description"],
                    "raw_response": data,
                }

            except httpx.TimeoutException:
                log(f"Timeout on {city} (attempt {attempt})", "WARN")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(BASE_DELAY * attempt)

            except httpx.HTTPStatusError as exc:
                log(f"HTTP {exc.response.status_code} on {city} (attempt {attempt})", "ERROR")
                if attempt < MAX_RETRIES and exc.response.status_code >= 500:
                    await asyncio.sleep(BASE_DELAY * attempt)
                else:
                    return None  # Non-retryable error

            except httpx.RequestError as exc:
                log(f"Network error on {city}: {exc} (attempt {attempt})", "ERROR")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(BASE_DELAY * attempt)

        log(f"All {MAX_RETRIES} attempts exhausted for {city}", "ERROR")
        return None


async def run_etl() -> dict:
    """Main ETL logic. Returns a summary dict."""
    start_time = time.monotonic()
    job_name = "fetch_weather"

    log(f"[{job_name}] Starting ETL run")
    log(f"[{job_name}] Cities: {', '.join(CITIES)}")

    # --- Connect to DB ---
    pool = await get_db()

    # --- Create run record ---
    run_id = await create_etl_run(pool, job_name)

    fetched_count = 0
    stored_count = 0
    errors: list[str] = []

    # --- Rate limit: max 3 concurrent API calls ---
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    try:
        async with httpx.AsyncClient() as client:
            tasks = [
                fetch_city_weather(client, city, semaphore)
                for city in CITIES
            ]
            results = await asyncio.gather(*tasks)

            # --- Store results ---
            for city, result in zip(CITIES, results):
                fetched_count += 1 if result is not None else 0

                if result is None:
                    errors.append(f"{city}: fetch failed")
                    continue

                try:
                    await store_weather_data(pool, run_id, city, result)
                    stored_count += 1
                except Exception as exc:
                    errors.append(f"{city}: store failed: {exc}")

        # --- Determine final status ---
        if errors and stored_count == 0:
            status = "failed"
        elif errors:
            status = "success"  # Partial success
        else:
            status = "success"

        await complete_etl_run(
            pool, run_id, status,
            records_fetched=fetched_count,
            records_stored=stored_count,
            error_message="; ".join(errors[:5]) if errors else None,
        )

        duration = time.monotonic() - start_time
        log(f"[{job_name}] Completed: status={status} "
            f"fetched={fetched_count}/{len(CITIES)} stored={stored_count} "
            f"errors={len(errors)} duration={duration:.2f}s")

        return {
            "status": status,
            "fetched": fetched_count,
            "stored": stored_count,
            "errors": errors,
            "duration_s": round(duration, 2),
        }

    except Exception as exc:
        duration = time.monotonic() - start_time
        error_msg = f"Unhandled exception: {type(exc).__name__}: {exc}"
        log(f"[{job_name}] FATAL: {error_msg}", "CRITICAL")
        await complete_etl_run(
            pool, run_id, "failed",
            records_fetched=fetched_count,
            records_stored=stored_count,
            error_message=error_msg,
        )
        return {
            "status": "failed",
            "fetched": fetched_count,
            "stored": stored_count,
            "errors": [error_msg],
            "duration_s": round(duration, 2),
        }
    finally:
        await pool.close()


# --- Monitoring / Alerting ---

async def send_healthcheck(status: str, summary: dict) -> None:
    """Send a signal to Healthchecks.io (or similar monitoring service)."""
    if not HEALTHCHECKS_URL:
        return

    async with httpx.AsyncClient() as client:
        try:
            if status == "success":
                # Ping success endpoint
                await client.get(HEALTHCHECKS_URL, timeout=10)
            else:
                # Ping fail endpoint (triggers alert)
                await client.post(
                    f"{HEALTHCHECKS_URL}/fail",
                    json=summary,
                    timeout=10,
                )
                log(f"[MONITOR] Sent failure alert to {HEALTHCHECKS_URL}")
        except httpx.RequestError as exc:
            log(f"[MONITOR] Failed to send healthcheck: {exc}", "WARN")


async def send_alert(summary: dict) -> None:
    """
    Send an alert on failure.
    Supports multiple channels: Slack, email, PagerDuty, etc.
    """
    if summary["status"] == "success" and not summary["errors"]:
        return  # All good, no alert needed

    # --- Example: Slack Alert ---
    slack_url = os.getenv("SLACK_ALERT_WEBHOOK")
    if slack_url:
        payload = {
            "text": f"🚨 ETL Job Alert: fetch_weather\n"
                    f"Status: {summary['status']}\n"
                    f"Errors: {summary['errors'][:3]}\n"
                    f"Duration: {summary.get('duration_s', '?')}s",
        }
        try:
            async with httpx.AsyncClient() as client:
                await client.post(slack_url, json=payload, timeout=10)
        except Exception as exc:
            log(f"[ALERT] Slack notification failed: {exc}", "WARN")


# --- Entry Point ---

async def main() -> int:
    """Main entry point. Returns exit code (0 = success, 1 = failure)."""
    # Run the ETL
    summary = await run_etl()

    # Send healthcheck (monitoring heartbeat)
    await send_healthcheck(summary["status"], summary)

    # Send alert on failure
    await send_alert(summary)

    # Exit code for cron compatibility
    return 0 if summary["status"] == "success" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

---

## Cron Configuration

```bash
# /etc/cron.d/etl-weather
# Run every 15 minutes, log to file, redirect stderr to stdout

*/15 * * * * root /usr/bin/python3 /opt/etl/fetch_weather.py >> /var/log/etl/weather.log 2>&1

# Alternative: every hour at :05 (staggered to avoid API bursts)
5 * * * * root /usr/bin/python3 /opt/etl/fetch_weather.py >> /var/log/etl/weather.log 2>&1
```

### Crontab Format Reference

```
# ┌───────── minute (0-59)
# │ ┌───────── hour (0-23)
# │ │ ┌───────── day of month (1-31)
# │ │ │ ┌───────── month (1-12)
# │ │ │ │ ┌───────── day of week (0-7) (Sun=0 or 7)
# │ │ │ │ │
# * * * * * command
```

### Log Rotation

```bash
# /etc/logrotate.d/etl
/var/log/etl/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 root root
}
```

---

## Docker + Systemd Alternative

### Docker Compose

```yaml
# docker-compose.yml
version: "3.8"
services:
  etl-worker:
    build: .
    command: python /app/etl/fetch_weather.py
    environment:
      - OPENWEATHER_API_KEY=${OPENWEATHER_API_KEY}
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/etldb
      - HEALTHCHECKS_URL=${HEALTHCHECKS_URL}
      - SLACK_ALERT_WEBHOOK=${SLACK_ALERT_WEBHOOK}
    env_file:
      - .env
    depends_on:
      - db
    restart: unless-stopped
```

### Systemd Timer (alternative to cron)

```ini
# /etc/systemd/system/etl-weather.service
[Unit]
Description=Weather ETL Job
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/etl/fetch_weather.py
User=etl
Group=etl
Environment=PYTHONUNBUFFERED=1
StandardOutput=append:/var/log/etl/weather.log
StandardError=append:/var/log/etl/weather.log
```

```ini
# /etc/systemd/system/etl-weather.timer
[Unit]
Description=Run Weather ETL every 15 minutes
Requires=etl-weather.service

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with:
```bash
sudo systemctl daemon-reload
sudo systemctl enable etl-weather.timer
sudo systemctl start etl-weather.timer
```

---

## Monitoring & Alerting

### Query: Failed Runs in Last 24h

```sql
SELECT * FROM etl_runs
WHERE job_name = 'fetch_weather'
  AND status = 'failed'
  AND started_at >= NOW() - INTERVAL '24 hours'
ORDER BY started_at DESC;
```

### Query: Last 10 Runs

```sql
SELECT id, status, records_fetched, records_stored,
       error_message, duration_ms,
       started_at, finished_at
FROM etl_runs
WHERE job_name = 'fetch_weather'
ORDER BY started_at DESC
LIMIT 10;
```

### Prometheus Metrics (Optional)

```python
# Expose metrics via a simple HTTP endpoint for Prometheus scraping
from prometheus_client import Counter, Gauge, Histogram, generate_latest

etl_runs_total = Counter("etl_runs_total", "Total ETL runs", ["job", "status"])
etl_duration_seconds = Histogram("etl_duration_seconds", "ETL run duration", ["job"])
etl_records_stored = Gauge("etl_records_stored", "Records stored per run", ["job"])
```

---

## Key Takeaways

- **Always handle rate limits** (HTTP 429) with `Retry-After` header respect.
- **Exponential backoff** with jitter prevents thundering herd on retries.
- **Database transaction per run** gives observability into success/failure/partial results.
- **Semaphore-based concurrency** limits parallel API calls without blocking the event loop.
- **Healthchecks.io** or similar provides dead-man's-switch monitoring (if the cron doesn't ping, alert).
- **Structured logging** to stdout (captured by cron's redirect) is simpler and more reliable than file logging.
- **Exit codes** (0 for success, 1 for failure) let cron/systemd know the run status.
- **Alert on failure** via Slack/email/PagerDuty so you know when data stops flowing.
