#!/usr/bin/env python3
"""Langfuse health watchdog — silent when healthy, noisy when down.

Runs every hour as a no_agent cron job. Produces output only on failure.
"""
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

COMPOSE_DIR = "/Users/luke/langfuse"
WEB_URL = "http://localhost:3000"
TIMEOUT = 10


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

    if failures:
        for f in failures:
            print(f, flush=True)
        print(f"@{time.strftime('%H:%M')}", flush=True)
        sys.exit(1)

    # Healthy — silent exit (no output = no notification)
    sys.exit(0)


if __name__ == "__main__":
    main()
