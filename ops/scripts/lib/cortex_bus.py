#!/usr/bin/env python3
"""
cortex_bus.py — Shared bus interaction library for fleet scripts.

Provides send/read/archive/list_queues functions using the Agent Bus HTTP API.
Bus URL is read from cortex-bus.conf (CORTEX_BUS_URL). No local fallback.
Config file location: $CORTEX_DEPLOY_HOME/cortex-bus.conf or ~/.hermes-cortex/cortex-bus.conf

Usage:
    from lib.cortex_bus import bus_send, bus_read, bus_archive, bus_list_queues
"""

import base64
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONFIG_FILE = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex")) / "cortex-bus.conf"


def _read_config(key: str) -> str:
    """Read a value from cortex-bus.conf by key."""
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            if line.startswith(f"{key}="):
                val = line.split("=", 1)[1].strip()
                # Strip surrounding quotes (single or double) from config values
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                return val
    return os.environ.get(key, "")


BUS_URL = os.environ.get("CORTEX_BUS_URL", "") or _read_config("CORTEX_BUS_URL")
BUS_FALLBACK_URL = os.environ.get("CORTEX_BUS_FALLBACK_URL", "") or _read_config("CORTEX_BUS_FALLBACK_URL")
raw_auth = os.environ.get("CORTEX_BUS_AUTH", "") or _read_config("CORTEX_BASIC_AUTH")
raw_token = os.environ.get("CORTEX_BUS_TOKEN", "") or _read_config("CORTEX_BUS_TOKEN")

# Support both CORTEX_BASIC_AUTH and CORTEX_BUS_AUTH key names
if not raw_auth:
    raw_auth = _read_config("CORTEX_BUS_AUTH")

CORTEX_BUS_AUTH = raw_auth
CORTEX_BUS_TOKEN = raw_token

if not BUS_URL:
    raise RuntimeError(
        "CORTEX_BUS_URL not configured. Set in cortex-bus.conf or CORTEX_BUS_URL env var. "
        f"(checked: {CONFIG_FILE})"
    )


def _get_auth_header() -> tuple[str, str]:
    """Return (scheme, credentials) for Authorization header."""
    if CORTEX_BUS_TOKEN:
        return ("Bearer", CORTEX_BUS_TOKEN)
    if CORTEX_BUS_AUTH:
        basic = base64.b64encode(CORTEX_BUS_AUTH.encode()).decode()
        return ("Basic", basic)
    return ("Basic", "")


def _bus_post(endpoint: str, payload: dict, fallback: bool = False) -> dict:
    """POST to bus API with retry and exponential backoff."""
    scheme, creds = _get_auth_header()
    base_url = BUS_FALLBACK_URL if (fallback and BUS_FALLBACK_URL) else BUS_URL
    url = f"{base_url}{endpoint}"
    data = json.dumps(payload).encode()
    last_error = ""

    # When fallback is available, reduce primary retries so failover is faster
    max_attempts = 1 if (not fallback and BUS_FALLBACK_URL) else 3
    for attempt in range(max_attempts):
        try:
            req = Request(url, data=data, headers={
                "Content-Type": "application/json",
                "Authorization": f"{scheme} {creds}" if creds else "",
            })
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            # If Bearer gets 401/403 and Basic auth is available, try Basic on same URL
            if (
                not fallback
                and e.code in (401, 403)
                and scheme == "Bearer"
                and CORTEX_BUS_AUTH
            ):
                basic_creds = base64.b64encode(CORTEX_BUS_AUTH.encode()).decode()
                try:
                    req2 = Request(url, data=data, headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Basic {basic_creds}",
                    })
                    with urlopen(req2, timeout=15) as resp2:
                        return json.loads(resp2.read().decode())
                except Exception:
                    pass  # Basic also failed — fall through to retry/fallback
            last_error = str(e)
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
        except URLError as e:
            last_error = str(e)
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            last_error = str(e)
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)

    # Fallback attempt if available
    if not fallback and BUS_FALLBACK_URL:
        try:
            return _bus_post(endpoint, payload, fallback=True)
        except Exception:
            pass

    raise ConnectionError(f"Bus API unreachable after 3 attempts: {last_error}")


def bus_send(queue: str, message_body: dict) -> dict | None:
    """Send a message to a bus queue. Returns response dict or None on failure."""
    try:
        payload = {
            "queue": queue,
            "message": json.dumps(message_body),
            "correlation_id": message_body.get("correlation_id", ""),
        }
        return _bus_post("/api/pgmq/send", payload)
    except (ConnectionError, Exception) as e:
        return None


def bus_read(queue: str, vt: int = 60) -> dict | None:
    """Read one message from a bus queue.

    Auto-parses the PGMQ body (JSON string) into a dict so all consumers
    get structured data without needing to know about the wire format.

    Returns the full message dict with 'body' already parsed, or None.
    """
    try:
        payload = {"queue": queue, "vt": vt}
        result = _bus_post("/api/pgmq/read", payload)
        if result and result.get("msg_id"):
            # PGMQ stores messages as JSON strings — auto-parse the body
            if isinstance(result.get("body"), str):
                try:
                    result["body"] = json.loads(result["body"])
                except (json.JSONDecodeError, TypeError):
                    pass
            # Normalize None body to empty dict so consumers never crash on body.get()
            if result.get("body") is None:
                result["body"] = {}
            # Normalize None correlation_id to empty string for subscript safety
            if result.get("correlation_id") is None:
                result["correlation_id"] = ""
            return result
        return None
    except (ConnectionError, Exception):
        return None


def bus_archive(queue: str, msg_id: str) -> bool:
    """Archive a processed message. Returns True on success."""
    if not msg_id:
        return False
    try:
        _bus_post("/api/pgmq/archive", {"queue": queue, "msg_id": msg_id})
        return True
    except (ConnectionError, Exception):
        return False


def bus_list_queues() -> list[dict]:
    """List all bus queues. Returns list of dicts with name, depth, dlq, processing."""
    try:
        scheme, creds = _get_auth_header()
        req = Request(f"{BUS_URL}/api/pgmq/queues",
                      headers={"Authorization": f"{scheme} {creds}"},
                      method="GET")
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        queues = data.get("queues", []) if isinstance(data, dict) else data
        return queues
    except Exception:
        return []


def bus_health() -> dict:
    """Check bus health endpoint — tries primary, then fallback."""
    scheme, creds = _get_auth_header()

    for base_url in (BUS_URL, BUS_FALLBACK_URL):
        if not base_url:
            continue
        try:
            req = Request(f"{base_url}/health",
                          headers={"Authorization": f"{scheme} {creds}"},
                          method="GET")
            with urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            continue
    return {"status": "unreachable"}
