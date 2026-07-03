---
language: python
tags: [stripe, webhooks, payments, events]
title: Stripe Webhooks
description: Endpoint setup, signature verification, event types (checkout.session.completed, subscription.*), idempotency, retry handling
source: pattern
---

# Stripe Webhooks

## Setup

```python
# pip install stripe fastapi
import stripe
from fastapi import FastAPI, HTTPException, Request
from typing import Callable, Dict

# Set your secret key
stripe.api_key = "sk_test_..."

# Webhook signing secret from Stripe Dashboard > Webhooks > your endpoint > Signing secret
STRIPE_WEBHOOK_SECRET = "whsec_..."

app = FastAPI()
```

## Webhook Endpoint with Signature Verification

```python
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint with signature verification.

    Stripe sends events as POST requests with a `stripe-signature` header.
    We verify this signature to ensure the request is genuinely from Stripe.
    """
    payload_body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload_body,
            sig_header=sig_header,
            webhook_secret=STRIPE_WEBHOOK_SECRET,
        )
    except ValueError as e:
        # Invalid payload
        print(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        print(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Process the verified event
    return await process_stripe_event(event)
```

## Event Router

```python
# Registry of event handlers
event_handlers: Dict[str, Callable] = {}


def on_event(event_type: str):
    """Decorator to register a webhook event handler."""
    def decorator(func: Callable):
        event_handlers[event_type] = func
        return func
    return decorator


async def process_stripe_event(event: stripe.Event):
    """Route event to the appropriate handler."""
    event_type = event.type
    handler = event_handlers.get(event_type)

    if handler:
        try:
            await handler(event.data.object)
            return {"status": "success", "event_type": event_type}
        except Exception as e:
            # Log the error but return 200 to Stripe (prevent retries for logged errors)
            print(f"Error handling {event_type}: {e}")
            return {"status": "error", "event_type": event_type, "detail": str(e)}
    else:
        # Unhandled event types — acknowledge receipt so Stripe doesn't retry
        print(f"Unhandled event type: {event_type}")
        return {"status": "unhandled", "event_type": event_type}
```

## Common Event Handlers

### Checkout Events

```python
@on_event("checkout.session.completed")
async def handle_checkout_completed(session: stripe.checkout.Session):
    """
    One-time payment completed successfully.

    This fires after the customer completes the Checkout flow.
    For card payments, payment_status will be "paid" immediately.
    For delayed payment methods (bank transfer, etc.), payment_status may be "unpaid".
    """
    print(f"Checkout completed: {session.id}")
    print(f"  Customer: {session.customer_details.email}")
    print(f"  Amount: {session.amount_total} {session.currency}")
    print(f"  Payment status: {session.payment_status}")
    print(f"  Metadata: {session.metadata}")

    # Fulfill the order
    if session.payment_status == "paid":
        await fulfill_order(session)


@on_event("checkout.session.async_payment_succeeded")
async def handle_checkout_async_payment_succeeded(session: stripe.checkout.Session):
    """
    Delayed payment method succeeded (e.g., bank transfer, SEPA debit).
    This is the second event for these payment methods.
    """
    print(f"Async payment succeeded: {session.id}")
    await fulfill_order(session)


@on_event("checkout.session.async_payment_failed")
async def handle_checkout_async_payment_failed(session: stripe.checkout.Session):
    """
    Delayed payment method failed.
    """
    print(f"Async payment failed: {session.id}")
    await handle_failed_payment(session)
```

### Subscription Events

```python
@on_event("customer.subscription.created")
async def handle_subscription_created(subscription: stripe.Subscription):
    """A new subscription has been created."""
    print(f"Subscription created: {subscription.id}")
    print(f"  Customer: {subscription.customer}")
    print(f"  Status: {subscription.status}")
    print(f"  Current period: {subscription.current_period_start} → {subscription.current_period_end}")
    # Activate access for the customer


@on_event("customer.subscription.updated")
async def handle_subscription_updated(subscription: stripe.Subscription):
    """Subscription was updated (upgrade, downgrade, renew, etc.)."""
    print(f"Subscription updated: {subscription.id}")
    print(f"  Status: {subscription.status}")
    print(f"  Items: {[item.price.id for item in subscription.items.data]}")

    if subscription.status == "active":
        # Ensure customer access is granted
        pass
    elif subscription.status == "past_due":
        # Payment failed — try to collect or notify
        await handle_past_due_subscription(subscription)


@on_event("customer.subscription.deleted")
async def handle_subscription_deleted(subscription: stripe.Subscription):
    """Subscription was cancelled or expired."""
    print(f"Subscription deleted: {subscription.id}")
    # Revoke access for the customer


@on_event("customer.subscription.paused")
async def handle_subscription_paused(subscription: stripe.Subscription):
    """Subscription was paused."""
    print(f"Subscription paused: {subscription.id}")
    # Temporarily suspend access
```

### Invoice Events

```python
@on_event("invoice.paid")
async def handle_invoice_paid(invoice: stripe.Invoice):
    """
    An invoice has been paid.
    For subscriptions, this fires on every successful renewal.
    """
    print(f"Invoice paid: {invoice.id}")
    print(f"  Customer: {invoice.customer}")
    print(f"  Amount paid: {invoice.amount_paid} {invoice.currency}")
    print(f"  Subscription: {invoice.subscription}")
    print(f"  Period: {invoice.period_start} → {invoice.period_end}")

    # Update billing history
    # Extend subscription access period if needed


@on_event("invoice.payment_failed")
async def handle_invoice_payment_failed(invoice: stripe.Invoice):
    """
    Invoice payment failed.
    Stripe will automatically retry based on your retry settings.
    """
    print(f"Invoice payment failed: {invoice.id}")
    print(f"  Customer: {invoice.customer}")
    print(f"  Attempt count: {invoice.attempt_count}")
    print(f"  Next attempt: {invoice.next_payment_attempt}")

    # Notify customer about the failed payment
    # Their subscription will enter past_due status
    await notify_payment_failed(invoice)


@on_event("invoice.finalized")
async def handle_invoice_finalized(invoice: stripe.Invoice):
    """Invoice has been finalized and is ready for payment."""
    print(f"Invoice finalized: {invoice.id}")
```

### Payment Intent Events

```python
@on_event("payment_intent.succeeded")
async def handle_payment_intent_succeeded(payment_intent: stripe.PaymentIntent):
    """A PaymentIntent has succeeded."""
    print(f"Payment succeeded: {payment_intent.id}")
    print(f"  Amount: {payment_intent.amount} {payment_intent.currency}")
    print(f"  Payment method: {payment_intent.payment_method_types}")


@on_event("payment_intent.payment_failed")
async def handle_payment_intent_failed(payment_intent: stripe.PaymentIntent):
    """A PaymentIntent has failed."""
    error = payment_intent.last_payment_error
    print(f"Payment failed: {payment_intent.id}")
    print(f"  Error: {error.message if error else 'Unknown'}")
    print(f"  Code: {error.code if error else 'Unknown'}")
```

## Idempotency Handling

```python
import redis.asyncio as aioredis

# Set up Redis for idempotency keys
redis_client = aioredis.from_url("redis://localhost:6379", decode_responses=True)

# Track processed event IDs to ensure idempotency
PROCESSED_EVENTS_TTL = 86400 * 7  # 7 days (Stripe can send duplicates within this window)


async def is_event_processed(event_id: str) -> bool:
    """Check if we've already processed this event."""
    return await redis_client.exists(f"stripe:event:{event_id}") > 0


async def mark_event_processed(event_id: str):
    """Mark an event as processed to prevent duplicate handling."""
    await redis_client.setex(f"stripe:event:{event_id}", PROCESSED_EVENTS_TTL, "1")


@app.post("/webhooks/stripe/idempotent")
async def stripe_webhook_idempotent(request: Request):
    """
    Webhook endpoint with idempotency protection.
    Stripe may deliver the same event multiple times (especially during retries).
    """
    payload_body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload_body, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Idempotency check: skip if already processed
    if await is_event_processed(event.id):
        print(f"Duplicate event (already processed): {event.id} ({event.type})")
        return {"status": "already_processed", "event_id": event.id}

    # Process the event
    result = await process_stripe_event(event)

    # Mark as processed (only after successful handling)
    await mark_event_processed(event.id)

    return result
```

## Retry Handling & Logging

```python
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stripe-webhooks")


def log_stripe_event(event: stripe.Event, status: str):
    """Log webhook events for debugging and monitoring."""
    logger.info(
        f"Stripe Webhook | ID: {event.id} | Type: {event.type} | "
        f"Created: {datetime.fromtimestamp(event.created)} | "
        f"Livemode: {event.livemode} | Status: {status}"
    )


@app.post("/webhooks/stripe/logged")
async def stripe_webhook_logged(request: Request):
    """Webhook endpoint with logging and monitoring."""
    payload_body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload_body, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"Received event: {event.id} ({event.type})")

    try:
        result = await process_stripe_event(event)
        log_stripe_event(event, "success")
        return result
    except Exception as e:
        log_stripe_event(event, f"error: {e}")
        # Always return 200 to Stripe to acknowledge receipt
        # If we return non-200, Stripe will retry
        return {"status": "acknowledged", "event_type": event.type}
```

## Stripe CLI — Local Testing

```python
"""
# Test webhooks locally with the Stripe CLI:

# 1. Install Stripe CLI: https://stripe.com/docs/stripe-cli

# 2. Login
stripe login

# 3. Forward events to your local endpoint
stripe listen --forward-to localhost:8000/webhooks/stripe

# 4. In another terminal, trigger test events:
stripe trigger checkout.session.completed
stripe trigger customer.subscription.created
stripe trigger invoice.paid
stripe trigger payment_intent.succeeded

# 5. Or trigger an event with custom data:
stripe trigger checkout.session.completed \
  --add checkout_session:metadata.order_id=ORD-123

# Get your webhook signing secret:
stripe listen --print-secret
"""
```

## Helper Functions

```python
async def fulfill_order(session: stripe.checkout.Session):
    """Fulfill a completed order."""
    # Update database, grant access, send email, etc.
    print(f"✅ Fulfilling order: {session.id}")
    # await db.orders.update(session.id, {"status": "fulfilled"})
    # await email.send_confirmation(session.customer_details.email)


async def handle_failed_payment(session: stripe.checkout.Session):
    """Handle a failed payment."""
    print(f"❌ Payment failed for order: {session.id}")
    # await db.orders.update(session.id, {"status": "payment_failed"})
    # await email.send_failure_notice(session.customer_details.email)


async def handle_past_due_subscription(subscription: stripe.Subscription):
    """Handle a past-due subscription."""
    print(f"⚠️ Subscription past due: {subscription.id}")
    # Notify customer to update payment method
    # Stripe will auto-retry based on your retry schedule


async def notify_payment_failed(invoice: stripe.Invoice):
    """Notify customer about a failed invoice payment."""
    print(f"📧 Notify customer about failed payment: {invoice.id}")
    # await email.send_payment_failed(invoice.customer_email, invoice.hosted_invoice_url)
```