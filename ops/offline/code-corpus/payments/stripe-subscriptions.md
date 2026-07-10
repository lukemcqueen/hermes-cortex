---
language: python
tags: [stripe, subscriptions, recurring, billing]
title: Stripe Subscriptions
description: Create customer, subscribe to price, webhook handling for renewal/invoice.paid, cancellation, upgrade/downgrade proration
source: pattern
---

# Stripe Subscriptions

## Setup

```python
# pip install stripe fastapi
import stripe
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

stripe.api_key = "sk_test_..."
YOUR_DOMAIN = "http://localhost:8000"
STRIPE_WEBHOOK_SECRET = "whsec_..."

app = FastAPI()
```

## Create Customer

```python
class CreateCustomerRequest(BaseModel):
    email: str
    name: Optional[str] = None
    payment_method_id: Optional[str] = None  # If collecting payment method upfront


@app.post("/customers/create")
async def create_customer(req: CreateCustomerRequest):
    """Create a Stripe Customer."""
    try:
        customer = stripe.Customer.create(
            email=req.email,
            name=req.name or req.email.split("@")[0],
        )

        # If a payment method was provided, attach it
        if req.payment_method_id:
            stripe.PaymentMethod.attach(req.payment_method_id, customer=customer.id)
            stripe.Customer.modify(
                customer.id,
                invoice_settings={"default_payment_method": req.payment_method_id},
            )

        return {
            "customer_id": customer.id,
            "email": customer.email,
            "name": customer.name,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Subscribe to a Price

```python
class SubscribeRequest(BaseModel):
    customer_id: str
    price_id: str
    trial_days: Optional[int] = None
    coupon: Optional[str] = None
    metadata: Optional[dict] = None


@app.post("/subscriptions/create")
async def create_subscription(req: SubscribeRequest):
    """
    Create a subscription for a customer.

    This initiates recurring billing on the specified price.
    If the customer has a default payment method, the first invoice
    is created immediately.
    """
    try:
        subscription_params = {
            "customer": req.customer_id,
            "items": [{"price": req.price_id}],
            "metadata": req.metadata or {},
            "payment_behavior": "default_incomplete",
            "expand": ["latest_invoice.payment_intent"],
        }

        if req.trial_days:
            subscription_params["trial_period_days"] = req.trial_days

        if req.coupon:
            subscription_params["coupon"] = req.coupon

        subscription = stripe.Subscription.create(**subscription_params)

        return {
            "subscription_id": subscription.id,
            "status": subscription.status,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "trial_end": subscription.trial_end,
            "latest_invoice": {
                "id": subscription.latest_invoice.id,
                "payment_intent": subscription.latest_invoice.payment_intent.client_secret
                if subscription.latest_invoice.payment_intent else None,
                "status": subscription.latest_invoice.status,
            },
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Checkout-Based Subscription

```python
@app.post("/subscriptions/checkout")
async def create_subscription_checkout(price_id: str, customer_id: Optional[str] = None):
    """
    Create a Checkout Session for subscription signup.
    This lets Stripe handle the payment method collection.
    """
    try:
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,  # Optional: re-use existing customer
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{YOUR_DOMAIN}/subscriptions/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{YOUR_DOMAIN}/subscriptions/cancel",
            subscription_data={
                "metadata": {"source": "checkout"},
                "trial_period_days": 14,  # Optional trial
            },
        )

        return {"session_id": checkout_session.id, "url": checkout_session.url}
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Cancel Subscription

```python
class CancelSubscriptionRequest(BaseModel):
    subscription_id: str
    cancel_at_period_end: bool = True  # False = cancel immediately
    invoice_now: bool = True          # Generate final invoice if cancelling immediately
    prorate: bool = True              # Prorate the final invoice


@app.post("/subscriptions/cancel")
async def cancel_subscription(req: CancelSubscriptionRequest):
    """
    Cancel a subscription.

    cancel_at_period_end=True:  Subscription continues until the current period ends
    cancel_at_period_end=False: Cancels immediately, optionally generating a final invoice
    """
    try:
        if req.cancel_at_period_end:
            # Schedule cancellation at period end
            subscription = stripe.Subscription.modify(
                req.subscription_id,
                cancel_at_period_end=True,
            )
            message = "Subscription will be cancelled at the end of the billing period"
        else:
            # Cancel immediately
            subscription = stripe.Subscription.delete(
                req.subscription_id,
                invoice_now=req.invoice_now,
                prorate=req.prorate,
            )
            message = "Subscription cancelled immediately"

        return {
            "subscription_id": subscription.id,
            "status": subscription.status,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "message": message,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Upgrade / Downgrade with Proration

```python
class UpdateSubscriptionRequest(BaseModel):
    subscription_id: str
    new_price_id: str
    proration_behavior: str = "create_prorations"  # "none", "create_prorations", "always_invoice"


@app.post("/subscriptions/update")
async def update_subscription_plan(req: UpdateSubscriptionRequest):
    """
    Upgrade or downgrade a subscription to a different price/plan.

    Proration calculates the credit for unused time on the old plan
    and the charge for the new plan, resulting in a single invoice
    for the difference.
    """
    try:
        subscription = stripe.Subscription.retrieve(req.subscription_id)
        subscription_item_id = subscription.items.data[0].id

        updated_subscription = stripe.Subscription.modify(
            req.subscription_id,
            items=[{
                "id": subscription_item_id,
                "price": req.new_price_id,
            }],
            proration_behavior=req.proration_behavior,
            payment_behavior="pending_if_incomplete",
            expand=["latest_invoice"],
        )

        # The proration invoice
        latest_invoice = updated_subscription.latest_invoice

        return {
            "subscription_id": updated_subscription.id,
            "status": updated_subscription.status,
            "current_period_end": updated_subscription.current_period_end,
            "items": [
                {
                    "price_id": item.price.id,
                    "quantity": item.quantity,
                }
                for item in updated_subscription.items.data
            ],
            "proration_invoice": {
                "id": latest_invoice.id,
                "amount_due": latest_invoice.amount_due,
                "amount_paid": latest_invoice.amount_paid,
                "status": latest_invoice.status,
            } if latest_invoice else None,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/subscriptions/upgrade/preview")
async def preview_proration(customer_id: str, subscription_id: str, new_price_id: str):
    """
    Preview what the proration invoice would look like before upgrading.
    Useful for showing customers the charge/credit they'll receive.
    """
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        subscription_item_id = subscription.items.data[0].id

        # Simulate the invoice without actually changing the subscription
        upcoming = stripe.Invoice.upcoming(
            customer=customer_id,
            subscription=subscription_id,
            subscription_items=[{
                "id": subscription_item_id,
                "price": new_price_id,
            }],
        )

        return {
            "amount_due": upcoming.amount_due,
            "amount_remaining": upcoming.amount_remaining,
            "subtotal": upcoming.subtotal,
            "total": upcoming.total,
            "lines": [
                {
                    "description": line.description,
                    "amount": line.amount,
                    "period": f"{line.period.start} → {line.period.end}",
                }
                for line in upcoming.lines.data
            ],
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Webhook Handling for Renewals & Invoice Events

```python
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle subscription-related webhook events."""
    payload_body = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload_body, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event.type
    data = event.data.object

    handlers = {
        "customer.subscription.created": handle_subscription_created,
        "customer.subscription.updated": handle_subscription_updated,
        "customer.subscription.deleted": handle_subscription_deleted,
        "invoice.paid": handle_invoice_paid,
        "invoice.payment_failed": handle_invoice_payment_failed,
        "invoice.finalized": handle_invoice_finalized,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(data)
        return {"status": "processed", "event_type": event_type}

    print(f"Unhandled event: {event_type}")
    return {"status": "unhandled", "event_type": event_type}
```

### Handler Implementations

```python
async def handle_subscription_created(subscription: stripe.Subscription):
    """New subscription created — grant access to the customer."""
    customer_id = subscription.customer
    plan = subscription.items.data[0].price.nickname or subscription.items.data[0].price.id

    print(f"✅ [Subscription Created] {subscription.id}")
    print(f"   Customer: {customer_id}")
    print(f"   Plan: {plan}")
    print(f"   Status: {subscription.status}")

    # Grant access in your system
    # await grant_subscription_access(customer_id, plan, subscription.current_period_end)


async def handle_subscription_updated(subscription: stripe.Subscription):
    """Subscription updated (upgrade, downgrade, reactivation, etc.)."""
    print(f"🔄 [Subscription Updated] {subscription.id}")
    print(f"   Status: {subscription.status}")
    print(f"   Cancel at period end: {subscription.cancel_at_period_end}")

    if subscription.status == "active" and subscription.cancel_at_period_end is False:
        # Subscription was reactivated (cancellation undone)
        print("   → Subscription reactivated")
    elif subscription.status == "past_due":
        print("   → Payment past due — notify customer")

    # Update access in your system
    # await sync_subscription_access(subscription)


async def handle_subscription_deleted(subscription: stripe.Subscription):
    """Subscription cancelled or expired — revoke access."""
    print(f"❌ [Subscription Deleted] {subscription.id}")
    # Revoke access
    # await revoke_subscription_access(subscription.customer)


async def handle_invoice_paid(invoice: stripe.Invoice):
    """
    Invoice paid successfully.

    For subscriptions, this fires on:
    - Initial signup
    - Every renewal/billing cycle
    - Upgrade/downgrade proration invoices
    """
    subscription_id = invoice.subscription
    customer_id = invoice.customer

    print(f"💰 [Invoice Paid] {invoice.id}")
    print(f"   Subscription: {subscription_id}")
    print(f"   Customer: {customer_id}")
    print(f"   Amount: {invoice.amount_paid} {invoice.currency}")
    print(f"   Period: {invoice.period_start} → {invoice.period_end}")
    print(f"   Billing reason: {invoice.billing_reason}")

    if invoice.billing_reason == "subscription_create":
        print("   → Initial subscription payment")
    elif invoice.billing_reason == "subscription_cycle":
        print("   → Renewal payment — extend access for another period")
    elif invoice.billing_reason == "subscription_update":
        print("   → Proration invoice for upgrade/downgrade")
    elif invoice.billing_reason == "subscription_threshold":
        print("   → Metered billing threshold reached")

    # Update customer's subscription period in your database
    # await extend_subscription_period(customer_id, subscription_id, invoice.period_end)


async def handle_invoice_payment_failed(invoice: stripe.Invoice):
    """
    Invoice payment failed.

    Stripe will auto-retry based on your payment retry schedule.
    Notify the customer to update their payment method.
    """
    subscription_id = invoice.subscription
    customer_id = invoice.customer

    print(f"⚠️ [Invoice Payment Failed] {invoice.id}")
    print(f"   Subscription: {subscription_id}")
    print(f"   Customer: {customer_id}")
    print(f"   Attempt count: {invoice.attempt_count}")
    print(f"   Next attempt: {invoice.next_payment_attempt}")

    # Notify customer
    # if invoice.attempt_count == 1:
    #     await notify_payment_failed_first_attempt(customer_id, invoice)
    # elif invoice.attempt_count >= 3:
    #     await notify_payment_failed_final_attempt(customer_id, invoice)


async def handle_invoice_finalized(invoice: stripe.Invoice):
    """Invoice finalized — about to be paid or sent to customer."""
    print(f"📄 [Invoice Finalized] {invoice.id}")
    print(f"   Amount due: {invoice.amount_due} {invoice.currency}")
```

## List & Manage Subscriptions

```python
@app.get("/subscriptions/list/{customer_id}")
async def list_customer_subscriptions(customer_id: str):
    """List all subscriptions for a customer."""
    try:
        subscriptions = stripe.Subscription.list(
            customer=customer_id,
            status="all",
            limit=100,
        )

        return {
            "subscriptions": [
                {
                    "id": sub.id,
                    "status": sub.status,
                    "current_period_start": sub.current_period_start,
                    "current_period_end": sub.current_period_end,
                    "cancel_at_period_end": sub.cancel_at_period_end,
                    "plan": sub.items.data[0].price.nickname if sub.items.data else None,
                    "price_id": sub.items.data[0].price.id if sub.items.data else None,
                    "quantity": sub.items.data[0].quantity if sub.items.data else 1,
                    "trial_end": sub.trial_end,
                }
                for sub in subscriptions
            ],
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/subscriptions/invoices/{customer_id}")
async def list_customer_invoices(customer_id: str, limit: int = 10):
    """List recent invoices for a customer."""
    try:
        invoices = stripe.Invoice.list(
            customer=customer_id,
            limit=limit,
        )

        return {
            "invoices": [
                {
                    "id": inv.id,
                    "amount_paid": inv.amount_paid,
                    "amount_due": inv.amount_due,
                    "currency": inv.currency,
                    "status": inv.status,
                    "created": inv.created,
                    "period_start": inv.period_start,
                    "period_end": inv.period_end,
                    "hosted_invoice_url": inv.hosted_invoice_url,
                    "invoice_pdf": inv.invoice_pdf,
                }
                for inv in invoices
            ],
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
```