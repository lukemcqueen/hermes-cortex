---
title: Webhook → Process → Store → Notify
description: Receive a webhook (Stripe/GitHub), verify signature, process event, store in database, notify via email/Slack/webhook response, with idempotency key handling.
language: python
tags: [glue-code, webhook, process, notify, events]
---

# Webhook → Process → Store → Notify

## Overview

A robust webhook receiver that: receives incoming webhooks (Stripe checkout, GitHub push, or custom), verifies signatures, processes and stores events in PostgreSQL, sends notifications (email, Slack, webhook response), and handles idempotency to prevent duplicate processing.

---

## Database Schema

```sql
-- 0001_webhook_events.sql
CREATE TABLE webhook_events (
    id                BIGSERIAL PRIMARY KEY,
    idempotency_key   TEXT NOT NULL UNIQUE,
    source            TEXT NOT NULL,        -- 'stripe', 'github', 'custom'
    event_type        TEXT NOT NULL,        -- 'checkout.session.completed', 'push', etc.
    event_id          TEXT NOT NULL,        -- upstream event ID (Stripe event id, GitHub delivery id)
    headers           JSONB NOT NULL DEFAULT '{}',
    raw_body          TEXT NOT NULL,
    parsed_payload    JSONB,
    status            TEXT NOT NULL DEFAULT 'received'
                      CHECK (status IN ('received', 'processing', 'completed', 'failed')),
    error_message     TEXT,
    processed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, event_id)
);

CREATE INDEX idx_webhook_status ON webhook_events(status);
CREATE INDEX idx_webhook_created ON webhook_events(created_at DESC);

-- 0002_notifications.sql
CREATE TABLE notifications (
    id              BIGSERIAL PRIMARY KEY,
    webhook_event_id BIGINT NOT NULL REFERENCES webhook_events(id),
    channel         TEXT NOT NULL,          -- 'email', 'slack', 'webhook_response'
    channel_target  TEXT,                   -- email address, slack channel, response URL
    subject         TEXT,
    body            TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'sent', 'failed')),
    error_message   TEXT,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## Webhook Receiver (FastAPI)

### Configuration

```python
# config.py
import os

class WebhookConfig:
    # Stripe
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_...")

    # GitHub
    GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "your-github-secret")

    # Custom webhook shared secret
    CUSTOM_WEBHOOK_SECRET: str = os.getenv("CUSTOM_WEBHOOK_SECRET", "shared-secret")

    # Notifications
    SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")
    DEFAULT_NOTIFICATION_EMAIL: str = os.getenv("NOTIFICATION_EMAIL", "admin@example.com")

    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.example.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")

webhook_config = WebhookConfig()
```

### Main Webhook Receiver

```python
# webhook_receiver.py
import hashlib
import hmac
import json
import time
import asyncio
from typing import Callable, Awaitable

import stripe
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
import httpx
import asyncpg

from config import webhook_config

app = FastAPI(title="Webhook Receiver")

# Database pool
pool: asyncpg.Pool | None = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(
        dsn="postgresql://postgres:postgres@localhost:5432/webhookdb",
        min_size=2,
        max_size=10,
    )

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()


# --- Webhook Handlers ---
# Each source has its own endpoint with signature verification.

@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks (checkout.session.completed, etc.)."""
    raw_body = await request.body()
    signature = request.headers.get("stripe-signature", "")
    payload = raw_body.decode("utf-8")

    # --- 1. Verify Signature ---
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=webhook_config.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    stripe_event_id = event["id"]
    event_type = event["type"]
    idempotency_key = f"stripe:{stripe_event_id}"

    # --- 2. Idempotency Check ---
    existing = await get_event_by_idempotency_key(idempotency_key)
    if existing:
        return JSONResponse(
            content={"status": "already_processed", "event_id": existing["id"]},
            status_code=200,
        )

    # --- 3. Store Raw Event ---
    event_record = await store_raw_event(
        idempotency_key=idempotency_key,
        source="stripe",
        event_type=event_type,
        event_id=stripe_event_id,
        headers=dict(request.headers),
        raw_body=payload,
        parsed_payload=event.get("data", {}).get("object", {}),
    )

    # --- 4. Process ---
    await process_event(event_record)

    return {"status": "received", "event_id": event_record["id"]}


@app.post("/webhooks/github")
async def github_webhook(request: Request):
    """Handle GitHub webhooks (push, pull_request, etc.)."""
    raw_body = await request.body()
    signature_256 = request.headers.get("x-hub-signature-256", "")
    event_type = request.headers.get("x-github-event", "ping")
    delivery_id = request.headers.get("x-github-delivery", "")
    payload = raw_body.decode("utf-8")

    # --- 1. Verify Signature ---
    expected_sig = "sha256=" + hmac.new(
        webhook_config.GITHUB_WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature_256, expected_sig):
        raise HTTPException(status_code=400, detail="Invalid signature")

    idempotency_key = f"github:{delivery_id}"

    # --- 2. Idempotency Check ---
    existing = await get_event_by_idempotency_key(idempotency_key)
    if existing:
        return JSONResponse(content={"status": "already_processed"}, status_code=200)

    # --- 3. Store ---
    parsed = json.loads(payload)
    event_record = await store_raw_event(
        idempotency_key=idempotency_key,
        source="github",
        event_type=event_type,
        event_id=delivery_id,
        headers=dict(request.headers),
        raw_body=payload,
        parsed_payload=parsed,
    )

    # --- 4. Process ---
    await process_event(event_record)

    return {"status": "received", "event_id": event_record["id"]}


@app.post("/webhooks/custom")
async def custom_webhook(request: Request):
    """Handle custom webhooks with HMAC-SHA256 signature."""
    raw_body = await request.body()
    signature = request.headers.get("x-webhook-signature", "")
    timestamp = request.headers.get("x-webhook-timestamp", "")
    payload = raw_body.decode("utf-8")

    # --- 1. Prevent replay attacks (max 5 min skew) ---
    try:
        event_time = int(timestamp)
        if abs(time.time() - event_time) > 300:
            raise HTTPException(status_code=400, detail="Timestamp too old")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid timestamp")

    # --- 2. Verify Signature ---
    msg = f"{timestamp}.{payload}".encode()
    expected_sig = hmac.new(
        webhook_config.CUSTOM_WEBHOOK_SECRET.encode(),
        msg,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        raise HTTPException(status_code=400, detail="Invalid signature")

    parsed = json.loads(payload)
    event_id = parsed.get("event_id", hashlib.md5(payload.encode()).hexdigest())
    event_type = parsed.get("event_type", "unknown")
    idempotency_key = f"custom:{event_id}"

    # --- 3. Idempotency Check ---
    existing = await get_event_by_idempotency_key(idempotency_key)
    if existing:
        return JSONResponse(content={"status": "already_processed"}, status_code=200)

    # --- 4. Store ---
    event_record = await store_raw_event(
        idempotency_key=idempotency_key,
        source="custom",
        event_type=event_type,
        event_id=event_id,
        headers=dict(request.headers),
        raw_body=payload,
        parsed_payload=parsed,
    )

    # --- 5. Process ---
    await process_event(event_record)

    return {"status": "received", "event_id": event_record["id"]}
```

---

## Database Operations

```python
# db.py
import asyncpg
from typing import Optional

pool: asyncpg.Pool | None = None

async def get_event_by_idempotency_key(key: str) -> Optional[dict]:
    """Check if an event with this idempotency key was already processed."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM webhook_events WHERE idempotency_key = $1",
            key,
        )
        return dict(row) if row else None


async def store_raw_event(
    idempotency_key: str,
    source: str,
    event_type: str,
    event_id: str,
    headers: dict,
    raw_body: str,
    parsed_payload: dict | None = None,
) -> dict:
    """Insert a new webhook event record."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO webhook_events
                (idempotency_key, source, event_type, event_id, headers, raw_body, parsed_payload, status)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb, 'received')
            RETURNING *
            """,
            idempotency_key,
            source,
            event_type,
            event_id,
            json.dumps(headers),
            raw_body,
            json.dumps(parsed_payload) if parsed_payload else None,
        )
        return dict(row)


async def update_event_status(event_id: int, status: str, error_message: str | None = None) -> None:
    """Update event processing status."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE webhook_events
            SET status = $2, error_message = $3, processed_at = NOW()
            WHERE id = $1
            """,
            event_id,
            status,
            error_message,
        )


async def store_notification(
    webhook_event_id: int,
    channel: str,
    channel_target: str | None,
    subject: str,
    body: str,
) -> dict:
    """Record a notification attempt."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO notifications
                (webhook_event_id, channel, channel_target, subject, body, status)
            VALUES ($1, $2, $3, $4, $5, 'pending')
            RETURNING *
            """,
            webhook_event_id,
            channel,
            channel_target,
            subject,
            body,
        )
        return dict(row)
```

---

## Event Processing & Notification

```python
# processor.py
import asyncio
import json
import smtplib
from email.mime.text import MIMEText
import httpx

from config import webhook_config

async def process_event(event: dict) -> None:
    """Process a received webhook event: business logic + notifications."""
    event_id = event["id"]
    source = event["source"]
    event_type = event["event_type"]
    payload = event["parsed_payload"] or {}

    # Mark as processing
    await update_event_status(event_id, "processing")

    try:
        # --- Business Logic Router ---
        if source == "stripe" and event_type == "checkout.session.completed":
            result = await handle_stripe_checkout_completed(payload)

        elif source == "github" and event_type == "push":
            result = await handle_github_push(payload)

        elif source == "github" and event_type == "pull_request":
            result = await handle_github_pull_request(payload)

        elif source == "custom":
            result = await handle_custom_event(payload)

        else:
            result = {"handled": False, "reason": f"Unknown event type: {event_type}"}

        # --- Notifications ---
        await send_notifications(event, result)

        # Mark as completed
        await update_event_status(event_id, "completed")
        print(f"[PROCESSED] event={event_id} type={event_type}")

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        print(f"[FAILED] event={event_id} error={error_msg}")
        await update_event_status(event_id, "failed", error_msg)


async def send_notifications(event: dict, result: dict) -> None:
    """Send notifications for a processed event."""
    event_id = event["id"]
    source = event["source"]
    event_type = event["event_type"]

    subject = f"[{source.upper()}] {event_type}"
    body = json.dumps({
        "event_id": event["id"],
        "source": source,
        "event_type": event_type,
        "result": result,
        "timestamp": event["created_at"].isoformat() if event.get("created_at") else None,
    }, indent=2)

    tasks = []

    # --- Slack Notification ---
    if webhook_config.SLACK_WEBHOOK_URL:
        tasks.append(notify_slack(event_id, subject, body))

    # --- Email Notification ---
    if webhook_config.SMTP_HOST:
        tasks.append(notify_email(event_id, subject, body))

    # Run notifications concurrently
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def notify_slack(event_id: int, subject: str, body: str) -> None:
    """Send a Slack notification via webhook."""
    slack_payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": subject},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"```{body[:3000]}```"},
            },
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                webhook_config.SLACK_WEBHOOK_URL,
                json=slack_payload,
                timeout=10,
            )
            resp.raise_for_status()
            await store_notification(event_id, "slack", "webhook", subject, body[:1000])
            print(f"[NOTIFY] Slack sent for event={event_id}")
    except Exception as exc:
        print(f"[NOTIFY] Slack failed for event={event_id}: {exc}")


async def notify_email(event_id: int, subject: str, body: str) -> None:
    """Send an email notification via SMTP."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = webhook_config.SMTP_USER
    msg["To"] = webhook_config.DEFAULT_NOTIFICATION_EMAIL

    try:
        loop = asyncio.get_event_loop()

        def _send():
            with smtplib.SMTP(webhook_config.SMTP_HOST, webhook_config.SMTP_PORT) as server:
                server.starttls()
                server.login(webhook_config.SMTP_USER, webhook_config.SMTP_PASS)
                server.send_message(msg)

        await loop.run_in_executor(None, _send)
        await store_notification(event_id, "email", webhook_config.DEFAULT_NOTIFICATION_EMAIL, subject, body[:1000])
        print(f"[NOTIFY] Email sent for event={event_id}")
    except Exception as exc:
        print(f"[NOTIFY] Email failed for event={event_id}: {exc}")
```

---

## Business Logic Handlers

```python
# handlers.py
async def handle_stripe_checkout_completed(payload: dict) -> dict:
    """Process a Stripe checkout.session.completed event."""
    session_id = payload.get("id")
    customer_email = payload.get("customer_details", {}).get("email")
    amount_total = payload.get("amount_total", 0)
    payment_status = payload.get("payment_status")

    print(f"[HANDLER] Stripe checkout completed: session={session_id} email={customer_email} amount={amount_total}")

    # --- Store in your orders table ---
    # await store_order(session_id, customer_email, amount_total / 100)

    # --- Trigger downstream actions ---
    # await grant_access_to_user(customer_email)
    # await update_subscription(session_id)

    return {
        "handled": True,
        "session_id": session_id,
        "customer_email": customer_email,
        "amount": amount_total / 100,
    }


async def handle_github_push(payload: dict) -> dict:
    """Process a GitHub push event."""
    ref = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "")
    commits = payload.get("commits", [])
    repository = payload.get("repository", {}).get("full_name", "unknown")

    print(f"[HANDLER] GitHub push: repo={repository} branch={branch} commits={len(commits)}")

    # --- Trigger CI/CD ---
    # await trigger_ci_pipeline(repository, branch)

    # --- Send deployment notification ---
    # await notify_deployment(repository, branch, commits)

    return {
        "handled": True,
        "repository": repository,
        "branch": branch,
        "commit_count": len(commits),
        "commits": [c.get("id")[:8] for c in commits],
    }


async def handle_github_pull_request(payload: dict) -> dict:
    """Process a GitHub pull_request event."""
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")
    pr_title = pr.get("title")
    repository = payload.get("repository", {}).get("full_name", "unknown")

    print(f"[HANDLER] GitHub PR: repo={repository} #{pr_number} {action}: {pr_title}")

    if action == "opened":
        # await assign_reviewer(repository, pr_number)
        # await add_labels(repository, pr_number, ["needs-review"])
        pass
    elif action == "closed" and payload.get("pull_request", {}).get("merged"):
        # await merge_cleanup(repository, pr_number)
        pass

    return {
        "handled": True,
        "repository": repository,
        "pr_number": pr_number,
        "action": action,
        "title": pr_title,
    }


async def handle_custom_event(payload: dict) -> dict:
    """Process a custom webhook event."""
    event_action = payload.get("action", "unknown")
    data = payload.get("data", {})

    print(f"[HANDLER] Custom event: action={event_action} data_keys={list(data.keys())}")

    # Custom processing logic
    # await process_custom_action(event_action, data)

    return {
        "handled": True,
        "action": event_action,
        "data_summary": str(data)[:200],
    }
```

---

## Testing with Sample Webhooks

### Using `curl`

```bash
# Stripe-like webhook
curl -X POST http://localhost:8000/webhooks/stripe \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: t=1234567890,v1=test_signature" \
  -d '{
    "id": "evt_test_123",
    "type": "checkout.session.completed",
    "data": {
      "object": {
        "id": "cs_test_abc",
        "amount_total": 2999,
        "payment_status": "paid",
        "customer_details": {"email": "customer@example.com"}
      }
    }
  }'

# GitHub-like webhook
curl -X POST http://localhost:8000/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=..." \
  -H "X-GitHub-Event: push" \
  -H "X-GitHub-Delivery: abc123" \
  -d '{
    "ref": "refs/heads/main",
    "commits": [{"id": "abc123def"}],
    "repository": {"full_name": "my-org/my-repo"}
  }'
```

### Using Python

```python
# test_webhook.py
import hmac
import hashlib
import requests
import json

def send_custom_webhook(payload: dict, secret: str, url: str = "http://localhost:8000/webhooks/custom"):
    import time
    body = json.dumps(payload)
    timestamp = str(int(time.time()))
    msg = f"{timestamp}.{body}".encode()
    signature = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

    resp = requests.post(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": timestamp,
        },
    )
    return resp.json()

# Test
result = send_custom_webhook(
    {"event_id": "test-001", "event_type": "user.created", "data": {"user_id": 42}},
    secret="shared-secret",
)
print(result)
```

---

## Key Takeaways

- **Signature verification** is mandatory — always verify webhooks before processing.
- **Idempotency keys** prevent duplicate processing from retried deliveries.
- **Stripe** provides `stripe.Webhook.construct_event()` for verification; **GitHub** uses HMAC-SHA256; **custom** webhooks should include timestamp + signature to prevent replay attacks.
- **Store the raw event** before processing so you can replay or debug later.
- **Notifications** (Slack, email) should be non-blocking and fire-and-forget.
- **Status tracking** (received → processing → completed/failed) provides observability.
- Always return a fast `200` to the webhook sender to acknowledge receipt, even if processing happens asynchronously.
