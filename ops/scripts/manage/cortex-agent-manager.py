#!/usr/bin/env python3.12
"""
Hermes Cortex Agent Manager — Enterprise credential provisioning.

Usage:
  cortex-agent-manager.py add <name> --role worker|orchestrator [--labels key=val,key2=val2]
  cortex-agent-manager.py remove <name> [--confirm]
  cortex-agent-manager.py list [--show-labels]
  cortex-agent-manager.py label set <name> <key>=<value> [<key>=<value> ...]
  cortex-agent-manager.py label unset <name> <key>
  cortex-agent-manager.py label show <name>

Manages: bus.tokens, bus.permissions, nginx htpasswd, agent queues.
Must be run on the orchestrator (Moses/Esther) with Postgres + nginx access.

Security: All tokens are SHA-256 hashed before storage (PBKDF2-HMAC).
          Secrets file is 600-permissioned. No plaintext tokens in Postgres.
"""

import argparse
import hashlib
import json
import logging
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("cortex-agent-manager")

# ── Paths ────────────────────────────────────────────────────
CORTEX_HOME = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex"))
SECRETS_FILE = CORTEX_HOME / "agent-secrets.yaml"
NGINX_HTPASSWD = Path("/etc/nginx/.hermes-htpasswd")
BUS_URL = os.environ.get("CORTEX_BUS_URL", "http://127.0.0.1:8903")

# ── Token management ──────────────────────────────────────────


def _hash_token(token: str) -> str:
    """SHA-256 PBKDF2 hash of a bearer token for storage."""
    return hashlib.pbkdf2_hmac("sha256", token.encode(), b"hermes-bus-salt", 100000).hex()


def _generate_token() -> str:
    """Generate a cryptographically random bearer token."""
    return "hbus_" + secrets.token_hex(32)


def _random_password(length: int = 16) -> str:
    """Generate a random alphanumeric password for nginx htpasswd."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _validate_agent_name(name: str) -> str:
    """Validate and normalize an agent name. Raises ValueError on invalid input."""
    if not name or not name.strip():
        raise ValueError("Agent name cannot be empty")
    cleaned = name.strip().lower()
    if not all(c.isalnum() or c in "-_" for c in cleaned):
        raise ValueError(
            f"Agent name '{cleaned}' contains invalid characters "
            "(use alphanumeric, hyphens, underscores)"
        )
    if len(cleaned) > 64:
        raise ValueError(f"Agent name too long ({len(cleaned)} chars, max 64)")
    return cleaned

# ── Postgres operations ───────────────────────────────────────


def _pg_execute(sql: str, params: tuple = ()) -> list:
    """Execute SQL via Docker exec into the gbrain Postgres container."""
    safe_sql = sql % params  # psycopg-style %s params converted to positional
    cmd = [
        "docker", "exec", "-i", "gbrain-postgres",
        "psql", "-U", "gbrain", "-d", "gbrain", "-t",
        "-c", safe_sql
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.error("SQL error: %s", result.stderr.strip())
            return []
        output = result.stdout.strip()
        rows = []
        for line in output.splitlines():
            line = line.strip()
            if line and not line.startswith(("ERROR", "WARNING", "NOTICE")):
                cells = [c.strip() for c in line.split("|")]
                rows.append(tuple(cells))
        return rows
    except FileNotFoundError:
        logger.critical("docker not found. Are you on the orchestrator machine?")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        logger.error("SQL timed out after 10s")
        return []

# ── Nginx htpasswd operations ─────────────────────────────────


def _add_htpasswd(agent_name: str, password: str) -> bool:
    """Add an nginx htpasswd entry. Returns True on success."""
    if not NGINX_HTPASSWD.exists():
        logger.warning(
            "%s not found — skipping htpasswd. "
            "Agent %s will only work with Bearer token auth.",
            NGINX_HTPASSWD, agent_name
        )
        return False

    try:
        result = subprocess.run(
            ["sudo", "htpasswd", "-bS", str(NGINX_HTPASSWD), agent_name, password],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["sudo", "htpasswd", "-b", str(NGINX_HTPASSWD), agent_name, password],
                capture_output=True, text=True, timeout=10
            )
        if result.returncode != 0:
            logger.error("htpasswd failed: %s", result.stderr.strip())
            print("  Try: sudo htpasswd -b /etc/nginx/.hermes-htpasswd <name> <password>")
            return False
        return True
    except FileNotFoundError:
        logger.error("htpasswd command not found. Install: sudo apt install apache2-utils")
        return False
    except OSError as e:
        logger.error("htpasswd error: %s", e)
        return False


def _remove_htpasswd(agent_name: str) -> bool:
    """Remove an nginx htpasswd entry."""
    if not NGINX_HTPASSWD.exists():
        return False
    try:
        result = subprocess.run(
            ["sudo", "htpasswd", "-D", str(NGINX_HTPASSWD), agent_name],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except OSError as e:
        logger.error("htpasswd removal error: %s", e)
        return False

# ── Queue operations ──────────────────────────────────────────


def _create_queue(queue_name: str) -> bool:
    """Create a queue via the bus API. Returns True on success."""
    try:
        import urllib.request
        data = json.dumps({"queue": queue_name}).encode()
        req = urllib.request.Request(
            f"{BUS_URL}/api/pgmq/queue",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (OSError, ConnectionError, json.JSONDecodeError) as e:
        logger.warning("Queue creation failed for '%s': %s", queue_name, e)
        return False


# ── Agent labels file ─────────────────────────────────────────


def _write_agent_labels(agent_name: str, labels: dict) -> None:
    """Write a local agent-labels.json for the handler to read during label checks.
    
    The labels file is written to the agent's CORTEX_HOME directory so
    agent-message-handler.py can read it without bus access.
    Labels are used for canary deployment targeting.
    """
    if not labels:
        return
    labels_path = CORTEX_HOME / "agent-labels.json"
    try:
        labels_path.write_text(json.dumps(labels, indent=2))
        labels_path.chmod(0o644)
        logger.info("Wrote agent labels to %s: %s", labels_path, labels)
    except (IOError, OSError) as e:
        logger.warning("Could not write agent labels file: %s", e)


# ── Secrets storage ───────────────────────────────────────────


def _store_secret(agent_name: str, secret_data: dict) -> None:
    """Store credentials for recovery in agent-secrets.yaml (600-permissioned)."""
    secrets = {}
    if SECRETS_FILE.exists():
        try:
            import yaml
            content = SECRETS_FILE.read_text()
            if content.strip():
                secrets = yaml.safe_load(content) or {}
        except (yaml.YAMLError, IOError) as e:
            logger.warning("Could not read secrets file, starting fresh: %s", e)
        except Exception as e:
            logger.warning("Unexpected error reading secrets: %s", e)

    if "agents" not in secrets:
        secrets["agents"] = {}
    secrets["agents"][agent_name] = secret_data

    try:
        import yaml
        SECRETS_FILE.write_text(yaml.dump(secrets, default_flow_style=False))
        SECRETS_FILE.chmod(0o600)
    except ImportError:
        fallback = SECRETS_FILE.with_suffix(".json")
        fallback.write_text(json.dumps(secrets, indent=2))
        fallback.chmod(0o600)
    except (IOError, OSError) as e:
        logger.error("Failed to write secrets file: %s", e)


def _read_secrets() -> dict:
    """Read the agent-secrets.yaml file. Returns dict or {} on failure."""
    if not SECRETS_FILE.exists():
        json_file = SECRETS_FILE.with_suffix(".json")
        if json_file.exists():
            try:
                return json.loads(json_file.read_text())
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Could not read JSON secrets: %s", e)
                return {}
        return {}

    try:
        import yaml
        return yaml.safe_load(SECRETS_FILE.read_text()) or {}
    except (yaml.YAMLError, IOError) as e:
        logger.warning("Could not read secrets: %s", e)
        return {}

# ── CLI commands ──────────────────────────────────────────────


def cmd_add(args):
    """Add a new agent — create token, permissions, htpasswd, queues."""
    if args is None:
        print("❌ Internal error: args is None")
        sys.exit(1)
    try:
        agent_name = _validate_agent_name(args.name)
    except ValueError as e:
        print(f"❌ Invalid agent name: {e}")
        sys.exit(1)

    # 1. Validate agent doesn't exist
    rows = _pg_execute("SELECT agent_name FROM bus.tokens WHERE agent_name = %s", (agent_name,))
    if rows:
        print(f"❌ Agent '{agent_name}' already exists. Use 'remove' first to re-create.")
        sys.exit(1)

    # 2. Generate credentials
    token = _generate_token()
    password = _random_password()
    token_hash = _hash_token(token)

    # 3. Determine role permissions
    can_admin = (args.role == "orchestrator")

    # Parse labels
    labels = {}
    if args.labels:
        for pair in args.labels.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                labels[k.strip()] = v.strip()

    # 4. Store token in bus.tokens
    _pg_execute(
        "INSERT INTO bus.tokens (agent_name, token_hash, is_active, rotated_at, expires_at) "
        "VALUES (%s, %s, true, now(), now() + INTERVAL '90 days')",
        (agent_name, token_hash)
    )

    # 5. Create permission row
    _pg_execute(
        "INSERT INTO bus.permissions (agent_name, can_send, can_read, can_archive, "
        "can_requeue, can_delete, can_admin, updated_at) "
        "VALUES (%s, true, true, true, true, %s, %s, now())",
        (agent_name, can_admin, can_admin)
    )

    # 6. Add nginx htpasswd
    htpasswd_ok = _add_htpasswd(agent_name, password)

    # 7. Create queues
    inbox = f"inbox_{agent_name}"
    dlq = f"inbox_{agent_name}_dlq"
    _create_queue(inbox)
    _create_queue(dlq)

    # 8. Store credentials for recovery
    secret_data = {
        "role": args.role,
        "token": token,
        "password": password,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "labels": labels,
    }
    if labels:
        try:
            _pg_execute(
                "UPDATE bus.permissions SET labels = %s::jsonb WHERE agent_name = %s",
                (json.dumps(labels), agent_name)
            )
        except Exception as e:
            logger.warning("Could not update bus labels: %s", e)
    
    # 8b. Write local labels file for agent label checks
    _write_agent_labels(agent_name, labels)
    
    _store_secret(agent_name, secret_data)

    # 9. Print config snippet
    print(f"\n✅ Agent '{agent_name}' ({args.role}) created successfully.")
    print(f"   Token: {token}")
    if htpasswd_ok:
        print(f"   HTPasswd: added to {NGINX_HTPASSWD}")
    print(f"   Queues: {inbox}, {dlq}")
    print(f"   Expires: {(datetime.now(timezone.utc).isoformat()[:10])} + 90 days")
    print()
    print("📋 Agent config snippet:")
    print("-" * 50)
    print(f"CORTEX_BUS_URL=https://your-domain.com:13004")
    print(f"CORTEX_BASIC_AUTH={agent_name}:{password}")
    print(f"CORTEX_BUS_FALLBACK_URL=https://your-domain.com:14004")
    print(f"CORTEX_BUS_TOKEN={token}")
    print(f"AGENT_NAME={agent_name}")
    print("-" * 50)
    print(f"\n   Credentials stored in {SECRETS_FILE} (orchestrator only)")


def cmd_remove(args):
    """Remove an agent — revoke token, remove permissions, htpasswd."""
    if args is None:
        print("❌ Internal error: args is None")
        sys.exit(1)
    try:
        agent_name = _validate_agent_name(args.name)
    except ValueError as e:
        print(f"❌ Invalid agent name: {e}")
        sys.exit(1)

    if not args.confirm:
        print(f"⚠️  This will revoke ALL credentials for '{agent_name}'."
              f" Use --confirm to proceed.")
        sys.exit(1)

    # Revoke token
    _pg_execute("UPDATE bus.tokens SET is_active = false WHERE agent_name = %s", (agent_name,))
    # Remove permissions
    _pg_execute("DELETE FROM bus.permissions WHERE agent_name = %s", (agent_name,))
    # Remove htpasswd
    _remove_htpasswd(agent_name)

    # Remove from secrets file
    secrets = _read_secrets()
    if "agents" in secrets and agent_name in secrets["agents"]:
        del secrets["agents"][agent_name]
        try:
            import yaml
            SECRETS_FILE.write_text(yaml.dump(secrets, default_flow_style=False))
        except (yaml.YAMLError, IOError) as e:
            logger.warning("Could not update secrets file: %s", e)

    print(f"✅ Agent '{agent_name}' removed. Token revoked, permissions deleted.")


def cmd_list(args):
    """List all agents with their roles and status."""
    if args is None:
        print("❌ Internal error: args is None")
        return
    rows = _pg_execute(
        "SELECT t.agent_name, t.is_active, "
        "  COALESCE(p.can_admin, false) as is_orch, "
        "  t.created_at::text, t.expires_at::text "
        "FROM bus.tokens t "
        "LEFT JOIN bus.permissions p ON t.agent_name = p.agent_name "
        "ORDER BY t.agent_name"
    )

    if not rows:
        print("No agents found.")
        return

    print(f"{'Agent':<20} {'Role':<14} {'Active':<8} {'Created':<20} {'Expires':<20}")
    print("-" * 82)
    for row in rows:
        name, active, is_orch, created, expires = row
        role = "orchestrator" if is_orch else "worker"
        active_str = "✅" if active else "❌"
        created_str = created[:10] if created else "-"
        expires_str = expires[:10] if expires else "-"
        print(f"{name:<20} {role:<14} {active_str:<8} {created_str:<20} {expires_str:<20}")


def cmd_label_set(args):
    """Set one or more labels on an agent."""
    try:
        agent_name = _validate_agent_name(args.name)
    except ValueError as e:
        print(f"❌ Invalid agent name: {e}")
        sys.exit(1)

    # Check agent exists
    if not _pg_execute("SELECT agent_name FROM bus.tokens WHERE agent_name = %s", (agent_name,)):
        print(f"❌ Agent '{agent_name}' not found.")
        sys.exit(1)

    # Build labels dict from key=value pairs
    labels = {}
    for pair in args.labels:
        if "=" in pair:
            k, v = pair.split("=", 1)
            labels[k.strip()] = v.strip()
        else:
            logger.warning("Ignoring label (no '=' delimiter): %s", pair)

    try:
        _pg_execute(
            "UPDATE bus.permissions SET labels = COALESCE(labels, '{}'::jsonb) || %s::jsonb "
            "WHERE agent_name = %s",
            (json.dumps(labels), agent_name)
        )
    except Exception as e:
        logger.info("labels column may not exist, attempting migration: %s", e)
        try:
            _pg_execute("ALTER TABLE bus.permissions ADD COLUMN IF NOT EXISTS labels jsonb DEFAULT '{}'")
            _pg_execute(
                "UPDATE bus.permissions SET labels = %s::jsonb WHERE agent_name = %s",
                (json.dumps(labels), agent_name)
            )
        except Exception as migrate_err:
            print(f"⚠️  Could not set labels: {migrate_err}")
            sys.exit(1)

    # Update secrets file
    secrets = _read_secrets()
    if "agents" in secrets and agent_name in secrets["agents"]:
        secrets["agents"][agent_name].setdefault("labels", {}).update(labels)
        try:
            import yaml
            SECRETS_FILE.write_text(yaml.dump(secrets, default_flow_style=False))
        except (IOError, yaml.YAMLError) as e:
            logger.warning("Could not update secrets: %s", e)

    print(f"✅ Labels set for '{agent_name}': {labels}")


def cmd_label_unset(args):
    """Remove a label from an agent."""
    try:
        agent_name = _validate_agent_name(args.name)
    except ValueError as e:
        print(f"❌ Invalid agent name: {e}")
        sys.exit(1)

    key = args.key
    try:
        _pg_execute(
            "UPDATE bus.permissions SET labels = labels - %s WHERE agent_name = %s",
            (key, agent_name)
        )
    except Exception as e:
        print(f"⚠️  Could not remove label: {e}")
        sys.exit(1)

    # Update secrets
    secrets = _read_secrets()
    if "agents" in secrets and agent_name in secrets["agents"]:
        secrets["agents"][agent_name].get("labels", {}).pop(key, None)
        try:
            import yaml
            SECRETS_FILE.write_text(yaml.dump(secrets, default_flow_style=False))
        except (IOError, yaml.YAMLError) as e:
            logger.warning("Could not update secrets: %s", e)

    print(f"✅ Label '{key}' removed from '{agent_name}'.")


def cmd_label_show(args):
    """Show all labels for an agent."""
    try:
        agent_name = _validate_agent_name(args.name)
    except ValueError as e:
        print(f"❌ Invalid agent name: {e}")
        sys.exit(1)

    rows = _pg_execute(
        "SELECT labels FROM bus.permissions WHERE agent_name = %s",
        (agent_name,)
    )
    if not rows:
        print(f"❌ Agent '{agent_name}' not found in permissions table.")
        sys.exit(1)

    labels = rows[0][0] if rows[0][0] else {}
    if isinstance(labels, str):
        try:
            labels = json.loads(labels)
        except json.JSONDecodeError:
            labels = {}

    if not labels:
        print(f"Agent '{agent_name}' has no labels.")
        return

    print(f"Labels for '{agent_name}':")
    for key, value in labels.items():
        print(f"  {key}={value}")


def main():
    parser = argparse.ArgumentParser(description="Hermes Cortex Agent Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # add
    add_parser = subparsers.add_parser("add", help="Add a new agent")
    add_parser.add_argument("name", help="Agent name")
    add_parser.add_argument("--role", choices=["worker", "orchestrator"],
                            default="worker", help="Agent role")
    add_parser.add_argument("--labels", help="Comma-separated key=value labels")

    # remove
    remove_parser = subparsers.add_parser("remove", help="Remove an agent")
    remove_parser.add_argument("name", help="Agent name")
    remove_parser.add_argument("--confirm", action="store_true", help="Confirm removal")

    # list
    list_parser = subparsers.add_parser("list", help="List all agents")
    list_parser.add_argument("--show-labels", action="store_true", help="Show agent labels")

    # label
    label_parser = subparsers.add_parser("label", help="Manage agent labels")
    label_sub = label_parser.add_subparsers(dest="label_cmd")

    label_set = label_sub.add_parser("set", help="Set labels")
    label_set.add_argument("name", help="Agent name")
    label_set.add_argument("labels", nargs="+", help="key=value pairs")

    label_unset = label_sub.add_parser("unset", help="Remove a label")
    label_unset.add_argument("name", help="Agent name")
    label_unset.add_argument("key", help="Label key to remove")

    label_show = label_sub.add_parser("show", help="Show agent labels")
    label_show.add_argument("name", help="Agent name")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "remove":
        cmd_remove(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "label":
        if args.label_cmd == "set":
            cmd_label_set(args)
        elif args.label_cmd == "unset":
            cmd_label_unset(args)
        elif args.label_cmd == "show":
            cmd_label_show(args)
        else:
            print("Usage: cortex-agent-manager.py label <set|unset|show> ...")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr
    )
    main()
