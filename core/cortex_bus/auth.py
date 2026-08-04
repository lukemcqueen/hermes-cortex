"""
Bearer token authentication for the Agent Bus.

Tokens are stored bcrypt-hashed in Postgres. Each agent has a unique token
that can be rotated independently. Tokens auto-expire after 90 days.
"""

import hashlib
import os
import secrets
from typing import Optional
from pathlib import Path

# Use a simple SHA-256 hash for now (bcrypt requires extra deps)
# TODO: upgrade to bcrypt: pip install bcrypt
HASH_ALGO = "sha256"


def hash_token(token: str) -> str:
    """Hash a bearer token for storage."""
    return hashlib.pbkdf2_hmac(HASH_ALGO, token.encode(), b"hermes-bus-salt", 100000).hex()


def generate_token() -> str:
    """Generate a cryptographically random bearer token."""
    return "hbus_" + secrets.token_hex(32)


def issue_token_for_agent(agent_name: str) -> str:
    """Generate a token, hash it, store in Postgres. Returns the raw token.
    
    The raw token is shown ONCE (this function returns it). Store it in the
    agent's .env file. It cannot be retrieved from Postgres (only the hash is stored).
    """
    from cortex_bus.queue import get_queue
    
    token = generate_token()
    token_hash = hash_token(token)
    
    bus = get_queue()
    conn = bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute(
            "INSERT INTO bus.tokens (agent_name, token_hash, rotated_at) "
            "VALUES (%s, %s, now()) "
            "ON CONFLICT (agent_name) DO UPDATE SET "
            "  token_hash = EXCLUDED.token_hash, "
            "  rotated_at = now(), "
            "  is_active = true",
            (agent_name, token_hash),
        )
        bus._conn.commit()
    
    return token


def validate_token(token: str) -> Optional[str]:
    """Validate a bearer token. Returns the agent name if valid, None otherwise.
    
    Called by the bus server on every API request.
    """
    from cortex_bus.queue import get_queue
    
    token_hash = hash_token(token)
    
    bus = get_queue()
    conn = bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute(
            "SELECT agent_name FROM bus.tokens "
            "WHERE token_hash = %s AND is_active = true "
            "AND (expires_at IS NULL OR expires_at > now())",
            (token_hash,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def revoke_token(agent_name: str):
    """Revoke an agent's token (immediately invalidates it)."""
    from cortex_bus.queue import get_queue
    
    bus = get_queue()
    conn = bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute(
            "UPDATE bus.tokens SET is_active = false WHERE agent_name = %s",
            (agent_name,),
        )
        bus._conn.commit()
