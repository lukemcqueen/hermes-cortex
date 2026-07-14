#!/usr/bin/env python3
"""Langfuse health watchdog — silent when healthy, noisy when down.

Checks:
  1. Docker daemon reachable
  2. All 6 Langfuse containers running (web, worker, postgres, redis, clickhouse, minio)
  3. Web UI responds HTTP 200
  4. ClickHouse merge failures — alerts on increase (state-tracked across runs)

Runs every hour as a no_agent cron job. Produces output only on failure.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

COMPOSE_DIR = str(Path.home() / "langfuse")
WEB_URL = "http://localhost:3000"
TIMEOUT = 10
CH_CONTAINER = "langfuse-clickhouse-1"
CH_STATE_FILE = str(Path.home() / ".hermes-cortex" / "state" / "langfuse-ch-merge.state")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd: list[str]) -> dict:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            cwd=COMPOSE_DIR,
        )
        return {"rc": r.returncode, "out": r.stdout.strip(), "err": r.stderr.strip()}
    except FileNotFoundError:
        return {"rc": -1, "out": "", "err": f"command not found: {cmd[0]}"}
    except subprocess.TimeoutExpired:
        return {"rc": -2, "out": "", "err": "timed out"}


def check_docker() -> str | None:
    """Return error string if Docker daemon unreachable."""
    r = run(["docker", "ps"])
    if r["rc"] != 0:
        return f"Docker daemon unreachable:\n{r['err']}"
    return None


def check_containers() -> str | None:
    """Return error string if expected Langfuse containers aren't running."""
    r = run(["docker", "ps", "--format", "{{.Names}}"])
    if r["rc"] != 0:
        return f"docker ps failed:\n{r['err']}"

    running = set(r["out"].splitlines())
    expected = {
        "langfuse-langfuse-web-1",
        "langfuse-langfuse-worker-1",
        "langfuse-postgres-1",
        "langfuse-redis-1",
        "langfuse-clickhouse-1",
        "langfuse-minio-1",
    }

    missing = expected - running
    if not missing:
        return None

    # Get detailed status of all langfuse containers
    r2 = run(["docker", "ps", "-a", "--filter", "name=langfuse", "--format", "{{.Names}}\t{{.Status}}"])
    statuses = r2["out"] if r2["rc"] == 0 else "(could not fetch)"
    return f"Missing containers: {', '.join(sorted(missing))}\n\nAll langfuse containers:\n{statuses}"


def check_web() -> str | None:
    """Return error string if web UI is unreachable or wrong status."""
    try:
        req = urllib.request.Request(WEB_URL, method="GET")
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        if resp.status != 200:
            return f"Langfuse web returned HTTP {resp.status}"
        return None
    except urllib.error.URLError as e:
        return f"Langfuse web unreachable ({WEB_URL}): {e.reason}"
    except Exception as e:
        return f"Langfuse web check failed: {e}"


def _ch_query(sql: str) -> str | None:
    """Run a ClickHouse query via docker exec. Returns stdout or None on failure."""
    try:
        r = subprocess.run(
            ["docker", "exec", CH_CONTAINER, "clickhouse-client", "--query", sql],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return r.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def check_clickhouse_merges() -> str | None:
    """Check ClickHouse merge failure metrics. Returns alert string or None.

    Uses a state file to track TotalMergeFailures between runs and detect
    increases. Also alerts on stuck bg threads with no merges running.
    """
    total = _ch_query("SELECT value FROM system.metrics WHERE metric = 'TotalMergeFailures'")
    if total is None:
        return None  # ClickHouse not reachable — already caught by container check

    total = total.strip()
    try:
        failures = int(total)
    except (ValueError, TypeError):
        return None

    # Read last known value from state file
    prev_failures = 0
    if os.path.exists(CH_STATE_FILE):
        try:
            prev_failures = int(Path(CH_STATE_FILE).read_text().strip())
        except (ValueError, OSError):
            pass

    alerts = []

    # Check for increase
    if failures > prev_failures:
        new_f = failures - prev_failures
        alerts.append(f"TotalMergeFailures: {failures} (+{new_f} since last check)")

        # Get detailed metrics
        details = _ch_query(
            "SELECT "
            "(SELECT value FROM system.metrics WHERE metric = 'TotalMergeFailures') AS tf, "
            "(SELECT value FROM system.metrics WHERE metric = 'NonAbortedMergeFailures') AS naf, "
            "(SELECT value FROM system.metrics WHERE metric = 'Merge') AS am, "
            "(SELECT value FROM system.metrics WHERE metric = 'BackgroundMergesAndMutationsPoolTask') AS pool, "
            "(SELECT value FROM system.metrics WHERE metric = 'MergeTreeBackgroundExecutorThreadsActive') AS bg"
        )
        if details:
            alerts.append(f"Details: {details}")

    # Check for stuck bg threads (prior failures + no merges running)
    if failures > 0:
        details = _ch_query(
            "SELECT "
            "(SELECT value FROM system.metrics WHERE metric = 'Merge') AS am, "
            "(SELECT value FROM system.metrics WHERE metric = 'BackgroundMergesAndMutationsPoolTask') AS pool, "
            "(SELECT value FROM system.metrics WHERE metric = 'MergeTreeBackgroundExecutorThreadsActive') AS bg"
        )
        if details:
            parts = details.split()
            if len(parts) >= 3:
                try:
                    am, pool, bg = int(parts[0]), int(parts[1]), int(parts[2])
                    if bg > 0 and am == 0 and pool == 0:
                        alerts.append(f"Stuck: {bg} bg threads active but no merges running ({failures} prior failures)")
                except ValueError:
                    pass

    # Update state
    Path(CH_STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(CH_STATE_FILE).write_text(str(failures))

    if alerts:
        return "🔴 ClickHouse merge issues:\n" + "\n".join(alerts)
    return None


def main():
    failures = []

    docker_err = check_docker()
    if docker_err:
        failures.append(f"🐳 Docker:\n{docker_err}")
    else:
        ctr_err = check_containers()
        if ctr_err:
            failures.append(f"📦 Containers:\n{ctr_err}")

        web_err = check_web()
        if web_err:
            failures.append(f"🌐 Web:\n{web_err}")

        ch_err = check_clickhouse_merges()
        if ch_err:
            failures.append(f"🛢️ ClickHouse:\n{ch_err}")

    if failures:
        for f in failures:
            print(f, flush=True)
        print(f"@{time.strftime('%H:%M')}", flush=True)
        sys.exit(1)

    # Healthy — silent exit (no output = no notification)
    sys.exit(0)


if __name__ == "__main__":
    main()
