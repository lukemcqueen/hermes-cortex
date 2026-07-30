"""
Bus alert helpers — send AGENTS.md reminders via the Agent Bus.

Manages repo→owner mapping loading, auth token reading, and
bus message dispatch with Bearer/Basic Auth fallback.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from .config import HOME, REPO_OWNERS_PATH, REPO_OWNERS_TEMPLATE, BUS_CONFIG_PATHS


def load_repo_owners() -> dict:
    """Load repo→agent mapping from repo-owners.yaml. Returns empty dict on failure.

    Priority: ~/.hermes-cortex/config/repo-owners.yaml (per-machine config)
    Fallback:  docs/templates/repo-owners.yaml (repo template)
    """
    paths_to_try = [REPO_OWNERS_PATH, REPO_OWNERS_TEMPLATE]
    for p in paths_to_try:
        if not p.exists():
            continue
        try:
            import yaml
            with open(p) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and "repos" in data:
                return data["repos"]
            return {}
        except Exception:
            print("expected — silently handled", file=sys.stderr)
    return {}


def read_bus_token() -> str:
    """Read bus Bearer token from env or config files. Returns empty string if not found."""
    token = os.environ.get("CORTEX_BUS_TOKEN", "")
    if token:
        return token
    for cfg_path in BUS_CONFIG_PATHS:
        if not cfg_path.exists():
            continue
        try:
            for line in cfg_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = (x.strip().strip("'\"").strip() for x in line.split("=", 1))
                v = re.sub(r"\s+#.*$", "", v).strip()
                if k == "CORTEX_BUS_TOKEN" and v:
                    return v
        except OSError:
            print("expected — silently handled", file=sys.stderr)
    return ""


def read_basic_auth() -> str:
    """Read Basic Auth credentials from env or config files."""
    for env_key in ("CORTEX_BUS_AUTH", "CORTEX_BASIC_AUTH", "CORTEX_INBOX_AUTH"):
        val = os.environ.get(env_key, "")
        if val:
            return val
    for cfg_path in BUS_CONFIG_PATHS:
        if not cfg_path.exists():
            continue
        try:
            for line in cfg_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = (x.strip().strip("'\"").strip() for x in line.split("=", 1))
                v = re.sub(r"\s+#.*$", "", v).strip()
                if k in ("CORTEX_BUS_AUTH", "CORTEX_BASIC_AUTH", "CORTEX_INBOX_AUTH") and v:
                    return v
        except OSError:
            print("expected — silently handled", file=sys.stderr)
    return ""


def send_bus_alert(
    repo_name: str, owner: str, bus_url: str, token: str, fallback_url: str = ""
) -> bool:
    """Send an AGENTS.md reminder message to the owning agent via the bus."""

    def _do_send(url: str) -> bool:
        payload = {
            "queue": f"inbox_{owner}",
            "message": {
                "from": "doctor",
                "subject": f"AGENTS.md missing: {repo_name}",
                "body": (
                    f"AGENTS.md is missing from ~/{repo_name}. "
                    f"This repo was detected as a git project you maintain.\n\n"
                    f"Please create ~/{repo_name}/AGENTS.md with agent guidelines for this project. "
                    f"Template: ~/hermes-cortex/docs/templates/AGENTS.seed.md"
                ),
                "topic": "development",
                "priority": "normal",
            },
            "priority": 0,
        }
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            req = urllib.request.Request(
                f"{url}/api/pgmq/send",
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
                return True
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError):
            pass  # expected — silently handled
        # Bearer failed — try Basic Auth
        basic_auth = read_basic_auth()
        if not basic_auth:
            return False
        encoded = base64.b64encode(basic_auth.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
        try:
            req = urllib.request.Request(
                f"{url}/api/pgmq/send",
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
                return True
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError):
            return False

    if _do_send(bus_url):
        return True
    if fallback_url:
        return _do_send(fallback_url)
    return False


def dispatch_bus_alerts(res):
    """After checks run, send bus alerts for actionable AGENTS.md findings."""
    owners = load_repo_owners()
    if not owners:
        print("  ℹ️  --bus-alert: no repo-owners.yaml found")
        print("       Create ~/.hermes-cortex/config/repo-owners.yaml from template:")
        print("       mkdir -p ~/.hermes-cortex/config")
        print("       cp ~/hermes-cortex/docs/templates/repo-owners.yaml ~/.hermes-cortex/config/repo-owners.yaml")
        return

    token = read_bus_token()
    basic_auth_val = read_basic_auth()
    if not token and not basic_auth_val:
        print(
            "  ℹ️  --bus-alert: no bus auth found "
            "(set CORTEX_BUS_TOKEN or CORTEX_BUS_AUTH in env or cortex-bus.conf)"
        )
        return

    primary_url = os.environ.get("CORTEX_BUS_URL", "")
    fallback_url = os.environ.get("CORTEX_BUS_FALLBACK_URL", "")

    if not primary_url:
        for cfg_path in BUS_CONFIG_PATHS:
            if not cfg_path.exists():
                continue
            try:
                for line in cfg_path.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = (x.strip().strip("'\"").strip() for x in line.split("=", 1))
                    v = re.sub(r"\s+#.*$", "", v).strip()
                    if k == "CORTEX_BUS_URL" and v:
                        primary_url = v
                        break
            except OSError:
                print("expected — silently handled", file=sys.stderr)
            if primary_url:
                break

    if not fallback_url:
        for cfg_path in BUS_CONFIG_PATHS:
            if not cfg_path.exists():
                continue
            try:
                for line in cfg_path.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = (x.strip().strip("'\"'").strip() for x in line.split("=", 1))
                    v = re.sub(r"\s+#.*$", "", v).strip()
                    if k == "CORTEX_BUS_FALLBACK_URL" and v:
                        fallback_url = v
                        break
            except OSError:
                print("expected — silently handled", file=sys.stderr)
            if fallback_url:
                break

    if not primary_url and not fallback_url:
        print(
            "  ℹ️  --bus-alert: no bus URL configured — "
            "set CORTEX_BUS_URL (Moses) or CORTEX_BUS_FALLBACK_URL (Esther)"
        )
        return

    bus_url = primary_url or fallback_url

    sent = 0
    skipped = 0
    for c in res.checks:
        name = c["name"]
        status = c["status"]
        if not name.startswith("AGENTS.md (") or not name.endswith(")") or status not in ("WARN", "FAIL"):
            continue
        repo_name = name[len("AGENTS.md ("):-1]
        owner = owners.get(repo_name)
        if not owner:
            skipped += 1
            continue
        if send_bus_alert(repo_name, owner, bus_url, token, fallback_url=fallback_url):
            sent += 1

    if sent > 0:
        print(f"  📬 Bus alerts sent: {sent} message(s) to owning agent(s)")
    if skipped > 0:
        print(f"  ℹ️  {skipped} repo(s) have no owner in repo-owners.yaml — skipped")
