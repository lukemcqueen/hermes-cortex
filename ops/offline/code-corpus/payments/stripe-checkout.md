---
language: python
tags: [stripe, payments, checkout, ecommerce]
title: Stripe Checkout
description: Create checkout session, success/cancel URLs, product + price IDs, webhook endpoint, fulfilling orders
source: pattern
---

# Stripe Checkout

## Setup

```python
# pip install stripe
import stripe
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional

# Initialize Stripe
stripe.api_key = "sk_test_..."
YOUR_DOMAIN = "http://localhost:8000"

app = FastAPI()
```

## Create Checkout Session

```python
class CheckoutItem(BaseModel):
    price_id: str  # e.g., "price_1Qw..."
    quantity: int = 1


class CreateCheckoutRequest(BaseModel):
    items: list[CheckoutItem]
    customer_email: Optional[str] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
    metadata: Optional[dict] = None


@app.post("/checkout/create")
async def create_checkout_session(req: CreateCheckoutRequest):
    """
    Create a Stripe Checkout Session for one-time payments.

    Returns the session URL to redirect the customer to.
    """
    try:
        line_items = [
            {"price": item.price_id, "quantity": item.quantity}
            for item in req.items
        ]

        checkout_session = stripe.checkout.Session.create(
            line_items=line_items,
            mode="payment",  # "payment" for one-time, "subscription" for recurring
            success_url=req.success_url or f"{YOUR_DOMAIN}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=req.cancel_url or f"{YOUR_DOMAIN}/checkout/cancel",
            customer_email=req.customer_email,
            metadata=req.metadata or {},
            # Optional: collect shipping address
            shipping_address_collection={"allowed_countries": ["US", "CA", "GB", "DE", "FR"]},
            # Optional: allow promo codes
            allow_promotion_codes=True,
            # Optional: automatic tax calculation
            automatic_tax={"enabled": True},
        )

        return {
            "session_id": checkout_session.id,
            "url": checkout_session.url,
            "amount_total": checkout_session.amount_total,
            "currency": checkout_session.currency,
        }

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Frontend redirect convenience endpoint
@app.get("/checkout/go/{price_id}")
async def quick_checkout(price_id: str):
    """Quick redirect to Stripe checkout for a single price ID."""
    return await create_checkout_session(
        CreateCheckoutRequest(items=[CheckoutItem(price_id=price_id)])
    )
```

## Product & Price Management

```python
@app.post("/products/create")
async def create_product(name: str, description: str = "", unit_amount: int = 1999, currency: str = "usd"):
    """
    Create a product and its price in Stripe.
    unit_amount is in cents (1999 = $19.99).
    """
    try:
        product = stripe.Product.create(
            name=name,
            description=description,
        )

        price = stripe.Price.create(
            product=product.id,
            unit_amount=unit_amount,
            currency=currency,
        )

        return {
            "product_id": product.id,
            "price_id": price.id,
            "name": product.name,
            "amount": f"{unit_amount / 100:.2f} {currency.upper()}",
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/products/list")
async def list_products():
    """List all active products with their current prices."""
    products = stripe.Product.list(active=True, limit=100)
    result = []
    for product in products:
        prices = stripe.Price.list(product=product.id, active=True)
        result.append({
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "images": product.images,
            "prices": [
                {
                    "id": p.id,
                    "amount": p.unit_amount,
                    "currency": p.currency,
                    "interval": p.recurring.get("interval") if p.recurring else None,
                }
                for p in prices
            ],
        })
    return {"products": result}
```

## Success & Cancel Endpoints

```python
@app.get("/checkout/success")
async def checkout_success(session_id: str):
    """Display order confirmation after successful payment."""
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["line_items", "customer_details"],
        )

        return {
            "status": "success",
            "order_id": session.id,
            "customer_email": session.customer_details.email if session.customer_details else None,
            "amount_total": session.amount_total,
            "currency": session.currency,
            "payment_status": session.payment_status,
            "items": [
                {
                    "description": item.description,
                    "amount": item.amount_total,
                    "quantity": item.quantity,
                }
                for item in (session.line_items.data if session.line_items else [])
            ],
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/checkout/cancel")
async def checkout_cancel():
    """Display cancellation page."""
    return {
        "status": "cancelled",
        "message": "Your payment was cancelled. No charges were made.",
    }
```

## Webhook Endpoint — Fulfilling Orders

```python
from fastapi import Request, HTTPException
import hashlib
import hmac
import os

# Stripe webhook secret from Stripe Dashboard
STRIPE_WEBHOOK_SECRET = "whsec_..."


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.
    Required: Verify signature, then process the event.
    """
    payload_body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload_body,
            sig_header=sig_header,
            webhook_secret=STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        # Invalid payload
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    return await handle_stripe_event(event)


async def handle_stripe_event(event: stripe.Event):
    """Route Stripe events to their handlers."""
    event_type = event.type

    if event_type == "checkout.session.completed":
        session = event.data.object
        await fulfill_order(session)

    elif event_type == "checkout.session.async_payment_succeeded":
        session = event.data.object
        await fulfill_order(session)

    elif event_type == "checkout.session.async_payment_failed":
        session = event.data.object
        await handle_failed_payment(session)

    else:
        # Unhandled event type — log but don't error
        print(f"Unhandled event: {event_type}")

    return {"status": "received", "event_type": event_type}
```

## Fulfillment Logic

```python
async def fulfill_order(session: stripe.checkout.Session):
    """
    Fulfill the customer's order after successful payment.

    This is where you:
    1. Update your database with the order
    2. Grant access to digital goods
    3. Send confirmation emails
    4. Trigger shipping for physical goods
    """
    order_id = session.id
    customer_email = session.customer_details.email if session.customer_details else None
    metadata = session.metadata or {}
    payment_intent = session.payment_intent

    print(f"[FULFILLMENT] Processing order: {order_id}")
    print(f"[FULFILLMENT] Customer: {customer_email}")
    print(f"[FULFILLMENT] Amount: {session.amount_total} {session.currency}")

    # --- Database operations ---
    # In production:
    # order = await db.create_order(
    #     stripe_session_id=order_id,
    #     customer_email=customer_email,
    #     amount=session.amount_total,
    #     currency=session.currency,
    #     status="completed",
    #     metadata=metadata,
    # )
    #
    # For each line item:
    #   await db.add_order_item(order.id, item.description, item.amount_total, item.quantity)
    #   await grant_product_access(customer_email, item.price.id)
    #
    # await send_order_confirmation(customer_email, order)

    print(f"[FULFILLMENT] ✅ Order {order_id} fulfilled successfully")


async def handle_failed_payment(session: stripe.checkout.Session):
    """Handle a failed payment for a delayed payment method (e.g., bank transfer)."""
    order_id = session.id
    customer_email = session.customer_details.email if session.customer_details else None

    print(f"[FULFILLMENT] ❌ Payment failed for order: {order_id}")
    # await db.update_order_status(order_id, "payment_failed")
    # await send_payment_failed_email(customer_email, order_id)
```

## Complete Flow — Frontend Integration Example

```python
"""
# HTML/JavaScript frontend example:

<form id="checkout-form">
  <button id="checkout-button">Checkout — $19.99</button>
</form>

<script src="https://js.stripe.com/v3/"></script>
<script>
  const form = document.getElementById('checkout-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    // 1. Create checkout session via your backend
    const response = await fetch('/checkout/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items: [{ price_id: 'price_1Qw...', quantity: 1 }],
        metadata: { user_id: '123', order_ref: 'ORD-001' },
      }),
    });

    const { url } = await response.json();

    // 2. Redirect to Stripe Checkout
    window.location.href = url;
  });
</script>
"""
```

## Key Stripe API Reference

```python
# Common Stripe operations reference:

# Create a Checkout Session (payment mode)
checkout_session = stripe.checkout.Session.create(
    line_items=[{"price": "price_xxx", "quantity": 1}],
    mode="payment",
    success_url="https://example.com/success?session_id={CHECKOUT_SESSION_ID}",
    cancel_url="https://example.com/cancel",
)

# Retrieve a session
session = stripe.checkout.Session.retrieve("cs_test_xxx")

# List sessions
sessions = stripe.checkout.Session.list(limit=10)

# Create a PaymentIntent directly (if not using Checkout)
payment_intent = stripe.PaymentIntent.create(
    amount=1999,
    currency="usd",
    automatic_payment_methods={"enabled": True},
)

# Confirm a PaymentIntent
pi = stripe.PaymentIntent.confirm("pi_xxx", payment_method="pm_xxx")

# Refund a payment
refund = stripe.Refund.create(payment_intent="pi_xxx")
```