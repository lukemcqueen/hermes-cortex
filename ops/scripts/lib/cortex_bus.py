#!/usr/bin/env python3
"""
cortex_bus.py — Shared bus interaction library for fleet scripts.

Provides send/read/archive/list_queues functions using the Agent Bus HTTP API.
Bus URL is read from cortex-bus.conf (CORTEX_BUS_URL); when
CORTEX_BUS_FALLBACK_URL is set, sends automatically retry the fallback bus
per-call when the primary is unreachable (failover path, since 2026-08-04).
Config file location: $CORTEX_DEPLOY_HOME/cortex-bus.conf or ~/.hermes-cortex/cortex-bus.conf

Usage:
    from lib.cortex_bus import bus_send, bus_read, bus_archive, bus_list_queues
"""

import base64
import json
import logging
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
            logging.getLogger("cortex_bus").debug("HTTPError %d for Bearer auth — trying Basic fallback", e.code)
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
                except (HTTPError, URLError, OSError) as basic_err:
                    logging.getLogger("cortex_bus").debug(
                        "Basic auth fallback also failed for %s: %s", url, basic_err
                    )
            last_error = str(e)
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
        except URLError as e:
            last_error = str(e)
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as e:
            last_error = str(e)
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)

    # Fallback attempt if available
    if not fallback and BUS_FALLBACK_URL:
        try:
            return _bus_post(endpoint, payload, fallback=True)
        except (ConnectionError, OSError, json.JSONDecodeError) as fb_err:
            logging.getLogger("cortex_bus").warning("Fallback bus also failed: %s", fb_err)

    raise ConnectionError(f"Bus API unreachable after 3 attempts: {last_error}")


def bus_send(queue: str, message_body: dict) -> dict | None:
    """Send a message to a bus queue. Returns response dict or None on failure.
    
    Auto-serializes the inner `body` field (if it's a dict) so callers don't
    need to remember json.dumps() before passing it.
    """
    try:
        # Auto-serialize inner body if it's a dict (prevents double-encoding)
        inner_body = message_body.get("body")
        if isinstance(inner_body, dict):
            message_body["body"] = json.dumps(inner_body)
        
        payload = {
            "queue": queue,
            "message": json.dumps(message_body),
            "correlation_id": message_body.get("correlation_id", ""),
        }
        return _bus_post("/api/pgmq/send", payload)
    except (ConnectionError, OSError, json.JSONDecodeError) as e:
        logging.getLogger("cortex_bus").warning("bus_send failed: %s", e)
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
                    logging.getLogger("cortex_bus").debug("Body not JSON — preserved as-is")
            # Normalize None body to empty dict so consumers never crash on body.get()
            if result.get("body") is None:
                result["body"] = {}
            # Auto-parse inner body (the message's own `body` field)
            # Prevents the two-level JSON problem where outer body is parsed
            # but inner body is still a JSON string
            inner_body = result["body"].get("body")
            if isinstance(inner_body, str):
                try:
                    result["body"]["body"] = json.loads(inner_body)
                except (json.JSONDecodeError, TypeError):
                    logging.getLogger("cortex_bus").debug("Inner body not JSON — preserved as-is")
            # Normalize None correlation_id to empty string for subscript safety
            if result.get("correlation_id") is None:
                result["correlation_id"] = ""
            return result
        return None
    except (ConnectionError, OSError, json.JSONDecodeError) as e:
        logging.getLogger("cortex_bus").warning("bus_read failed: %s", e)
        return None


def bus_archive(queue: str, msg_id: str) -> bool:
    """Archive a processed message. Returns True on success."""
    if not msg_id:
        return False
    try:
        _bus_post("/api/pgmq/archive", {"queue": queue, "msg_id": msg_id})
        return True
    except (ConnectionError, OSError, json.JSONDecodeError) as e:
        logging.getLogger("cortex_bus").warning("bus_archive failed: %s", e)
        return False


def _bus_get(endpoint: str, fallback: bool = False) -> dict:
    """GET to bus API with Bearer→Basic auth fallback (mirrors _bus_post).

    Tries the primary URL with the configured auth scheme; on 401/403 with
    Bearer and a CORTEX_BASIC_AUTH available, retries with Basic (nginx
    validates Basic auth and sets X-Forwarded-User — Bearer is ignored
    through the proxy). When fallback=True, uses BUS_FALLBACK_URL instead.
    """
    scheme, creds = _get_auth_header()
    base_url = BUS_FALLBACK_URL if (fallback and BUS_FALLBACK_URL) else BUS_URL
    url = f"{base_url}{endpoint}"
    last_error = ""

    def _try(auth_scheme: str, auth_creds: str) -> dict:
        req = Request(url, headers={"Authorization": f"{auth_scheme} {auth_creds}"}, method="GET")
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    try:
        return _try(scheme, creds)
    except HTTPError as e:
        if e.code in (401, 403) and scheme == "Bearer" and CORTEX_BUS_AUTH:
            basic_creds = base64.b64encode(CORTEX_BUS_AUTH.encode()).decode()
            try:
                return _try("Basic", basic_creds)
            except (HTTPError, URLError, OSError, json.JSONDecodeError) as basic_err:
                logging.getLogger("cortex_bus").debug(
                    "Basic auth fallback also failed for %s: %s", url, basic_err
                )
        last_error = str(e)
    except (URLError, OSError, json.JSONDecodeError) as e:
        last_error = str(e)

    # Fallback bus attempt if available
    if not fallback and BUS_FALLBACK_URL:
        try:
            return _bus_get(endpoint, fallback=True)
        except (ConnectionError, OSError, json.JSONDecodeError) as fb_err:
            logging.getLogger("cortex_bus").warning("Fallback bus also failed: %s", fb_err)

    raise ConnectionError(f"Bus API unreachable: {last_error}")


def bus_list_queues() -> list[dict]:
    """List all bus queues. Returns list of dicts with name, depth, dlq, processing."""
    try:
        data = _bus_get("/api/pgmq/queues")
        queues = data.get("queues", []) if isinstance(data, dict) else data
        return queues
    except (OSError, json.JSONDecodeError, ConnectionError) as e:
        logging.getLogger("cortex_bus").warning("bus_list_queues failed: %s", e)
        return []


def bus_peek(queue: str, limit: int = 20) -> list[dict]:
    """Peek pending messages in a queue WITHOUT consuming them (non-destructive).

    Unlike bus_read (which marks messages 'processing' with a visibility
    timeout), bus_peek returns pending messages unchanged — safe for inbox
    inspection and exec-result polling loops.

    Auto-parses the PGMQ body (JSON string) into a dict for each message,
    mirroring bus_read's normalization.

    Returns a list of message dicts (possibly empty), or [] on failure.
    """
    try:
        data = _bus_get(f"/api/pgmq/peek/{queue}?limit={limit}")
        msgs = data.get("messages", []) if isinstance(data, dict) else []
        for m in msgs:
            if isinstance(m.get("body"), str):
                try:
                    m["body"] = json.loads(m["body"])
                except (json.JSONDecodeError, TypeError):
                    logging.getLogger("cortex_bus").debug("Body not JSON — preserved as-is")
            if m.get("body") is None:
                m["body"] = {}
        return msgs
    except (OSError, json.JSONDecodeError, ConnectionError) as e:
        logging.getLogger("cortex_bus").warning("bus_peek failed: %s", e)
        return []


def bus_archives(queue: str, limit: int = 20, since_minutes: int = 60) -> list[dict]:
    """Read recently archived messages from a queue (non-destructive).

    The live peek endpoint only sees 'pending' messages — results the
    handler already archived are invisible to it. This reads bus.archives
    so exec-result polling can find a result archived before the poll
    saw it (the archive-blindness hang, 2026-08-06).

    Returns a list of message dicts (possibly empty), or [] on failure.
    """
    try:
        data = _bus_get(
            f"/api/pgmq/archives/{queue}?limit={limit}&since_minutes={since_minutes}"
        )
        msgs = data.get("messages", []) if isinstance(data, dict) else []
        for m in msgs:
            if isinstance(m.get("body"), str):
                try:
                    m["body"] = json.loads(m["body"])
                except (json.JSONDecodeError, TypeError):
                    logging.getLogger("cortex_bus").debug("Body not JSON — preserved as-is")
            if m.get("body") is None:
                m["body"] = {}
        return msgs
    except (OSError, json.JSONDecodeError, ConnectionError) as e:
        logging.getLogger("cortex_bus").warning("bus_archives failed: %s", e)
        return []


def bus_health() -> dict:
    """Check bus health endpoint — tries primary, then fallback, with Bearer→Basic auth fallback."""
    scheme, creds = _get_auth_header()
    logger = logging.getLogger("cortex_bus")
    def _try(base_url: str, auth_scheme: str, auth_creds: str):
        req = Request(f"{base_url}/health",
                      headers={"Authorization": f"{auth_scheme} {auth_creds}"},
                      method="GET")
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    for base_url in (BUS_URL, BUS_FALLBACK_URL):
        if not base_url:
            continue
        try:
            return _try(base_url, scheme, creds)
        except HTTPError as e:
            if e.code in (401, 403) and scheme == "Bearer" and CORTEX_BUS_AUTH:
                # Mirror _bus_post: Bearer token may be stale — fall back to Basic auth
                basic_creds = base64.b64encode(CORTEX_BUS_AUTH.encode()).decode()
                try:
                    return _try(base_url, "Basic", basic_creds)
                except (HTTPError, URLError, OSError, json.JSONDecodeError) as basic_err:
                    logger.debug("bus_health: Basic auth fallback failed for %s: %s", base_url, basic_err)
                    continue
            logger.debug("bus_health: %s returned HTTP %d %s", base_url, e.code, e.reason)
            continue
        except (URLError, OSError, json.JSONDecodeError) as e:
            logger.debug("bus_health: %s unreachable: %s", base_url, e)
            continue
    return {"status": "unreachable"}
