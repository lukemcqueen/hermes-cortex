---
title: E-Commerce Checkout with Stripe
description: E-commerce checkout flow integrating Stripe Checkout. Features product catalog with prices, cart management, order creation on payment success, webhook handler for fulfillment, and email confirmation.
language: python
tags: [ecommerce, stripe, checkout, payments, orders]
---

# E-Commerce Checkout with Stripe

A complete e-commerce checkout flow integrating Stripe Checkout. Features a product catalog with pricing, server-side cart management, order creation on successful payment, Stripe webhook handling for fulfillment, and email confirmation.

## Architecture

```
┌─────────────┐    1. Browse products     ┌──────────────┐
│  React App  │ ─────────────────────────▶│  FastAPI      │
│  (Frontend) │                           │  Backend      │
│             │    2. Create checkout      │              │
│             │ ─────────────────────────▶│              │
│             │                           │  3. Create    │
│             │    4. Redirect to          │  Stripe       │
│             │    Stripe Checkout         │  Checkout     │
│             │ ◀─────────────────────────│  Session      │
│             │                           │              │
│             │  5. User pays on          │  6. Webhook   │
│             │  Stripe.com               │  confirms     │
│             │                           │  payment      │
│             │                           │              │
│             │                           │  7. Create    │
│             │                           │  Order + send │
│             │                           │  email        │
└─────────────┘                           └──────────────┘
```

## Backend

### `backend/app/__init__.py`

```python
from app.main import app
from app.routers import products, cart, checkout, webhooks, orders

app.include_router(products.router)
app.include_router(cart.router)
app.include_router(checkout.router)
app.include_router(webhooks.router)
app.include_router(orders.router)
```

### `backend/app/config.py`

```python
import os

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_...")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_...")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_...")

# App
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://shop:shop@localhost:5432/shop")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Email (SMTP)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.ethereal.email")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@example.com")
```

### `backend/app/database.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### `backend/app/models.py`

```python
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, JSON, Enum as SAEnum, func
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    price_cents = Column(Integer, nullable=False)  # Store in cents to avoid float issues
    currency = Column(String(3), default="usd")
    image_url = Column(String(500), default="")
    active = Column(Boolean, default=True)
    stripe_price_id = Column(String(100), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Cart(Base):
    """Persistent cart per session/user."""
    __tablename__ = "carts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), index=True, nullable=False)  # Anonymous cart
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    product = relationship("Product")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(20), unique=True, nullable=False, index=True)
    customer_email = Column(String(200), nullable=False)
    customer_name = Column(String(200), default="")
    status = Column(SAEnum(OrderStatus), default=OrderStatus.PENDING)
    total_cents = Column(Integer, nullable=False)
    currency = Column(String(3), default="usd")
    stripe_session_id = Column(String(100), unique=True, nullable=True)
    stripe_payment_intent = Column(String(100), nullable=True)
    items = Column(JSON, default=list)  # Snapshot of items at purchase time
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    fulfillments = relationship("Fulfillment", back_populates="order")


class Fulfillment(Base):
    """Tracks fulfillment actions (email sent, shipping label, etc.)."""
    __tablename__ = "fulfillments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    action = Column(String(50), nullable=False)  # "email_confirmation", "shipping", etc.
    status = Column(String(20), default="pending")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="fulfillments")
```

### `backend/app/schemas.py`

```python
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional, List


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    price_cents: int
    price_dollars: float  # Computed
    currency: str
    image_url: str
    active: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_price(cls, product) -> "ProductResponse":
        resp = cls.model_validate(product)
        resp.price_dollars = round(product.price_cents / 100.0, 2)
        return resp


class CartItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price_cents: int
    total_cents: int

    model_config = {"from_attributes": True}


class CartResponse(BaseModel):
    items: List[CartItemResponse]
    total_cents: int
    total_dollars: float
    item_count: int


class AddToCartRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=100)


class CreateCheckoutRequest(BaseModel):
    email: str
    name: Optional[str] = ""
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CheckoutResponse(BaseModel):
    url: str  # Stripe Checkout URL
    session_id: str


class OrderResponse(BaseModel):
    id: int
    order_number: str
    customer_email: str
    customer_name: str
    status: str
    total_cents: int
    total_dollars: float
    currency: str
    items: list
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
```

### `backend/app/services/email.py`

```python
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

from app.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL

logger = logging.getLogger(__name__)


def send_order_confirmation_email(to_email: str, order_number: str, items: list, total_dollars: float):
    """Send order confirmation via SMTP."""
    subject = f"Order Confirmation #{order_number}"
    items_html = "".join(
        f"<tr><td>{item.get('name', 'Item')}</td>"
        f"<td>{item.get('quantity', 1)}</td>"
        f"<td>${item.get('total_dollars', 0):.2f}</td></tr>"
        for item in items
    )

    html = f"""
    <html>
    <body>
        <h2>Thank you for your order!</h2>
        <p>Your order <strong>#{order_number}</strong> has been confirmed.</p>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;">
            <tr><th>Item</th><th>Qty</th><th>Total</th></tr>
            {items_html}
        </table>
        <p><strong>Total: ${total_dollars:.2f}</strong></p>
        <p>We'll notify you when your order ships.</p>
        <hr>
        <small>This is an automated confirmation.</small>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        if SMTP_HOST and SMTP_USER:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            logger.info(f"Confirmation email sent to {to_email} for order #{order_number}")
        else:
            logger.info(f"[DEV] Would send email to {to_email}: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
```

### `backend/app/services/order.py`

```python
import logging
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models import Order, OrderStatus, Fulfillment, Product
from app.services.email import send_order_confirmation_email
from app.config import APP_URL

logger = logging.getLogger(__name__)


def generate_order_number() -> str:
    """Generate a unique order number."""
    ts = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    return f"ORD-{ts}-{id(generate_order_number) % 10000:04d}"


def create_order_from_session(
    db: Session,
    stripe_session_id: str,
    customer_email: str,
    customer_name: str,
    payment_intent: str,
    line_items: list,
) -> Order:
    """Create an order from a completed Stripe Checkout session."""
    total_cents = sum(item["amount_total"] for item in line_items)
    items_snapshot = []

    for item in line_items:
        product = db.query(Product).filter(
            Product.stripe_price_id == item.get("price_id")
        ).first()
        items_snapshot.append({
            "product_id": product.id if product else None,
            "name": item.get("description", "Unknown"),
            "quantity": item.get("quantity", 1),
            "unit_price_cents": item.get("amount_total", 0) // max(item.get("quantity", 1), 1),
            "total_cents": item.get("amount_total", 0),
            "total_dollars": round(item.get("amount_total", 0) / 100.0, 2),
        })

    order = Order(
        order_number=generate_order_number(),
        customer_email=customer_email,
        customer_name=customer_name,
        status=OrderStatus.PAID,
        total_cents=total_cents,
        stripe_session_id=stripe_session_id,
        stripe_payment_intent=payment_intent,
        items=items_snapshot,
    )
    db.add(order)
    db.flush()

    # Record fulfillment: send email confirmation
    fulfillment = Fulfillment(
        order_id=order.id,
        action="email_confirmation",
        status="pending",
        details={"email": customer_email, "order_number": order.order_number},
    )
    db.add(fulfillment)
    db.commit()
    db.refresh(order)

    # Send email (async in production — use Celery/Redis Queue)
    try:
        send_order_confirmation_email(
            to_email=customer_email,
            order_number=order.order_number,
            items=items_snapshot,
            total_dollars=round(total_cents / 100.0, 2),
        )
        fulfillment.status = "completed"
        db.commit()
    except Exception as e:
        logger.error(f"Fulfillment failed for order #{order.order_number}: {e}")
        fulfillment.status = "failed"
        db.commit()

    return order
```

### `backend/app/routers/products.py`

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product
from app.schemas import ProductResponse

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/", response_model=list[ProductResponse])
def list_products(active_only: bool = True, db: Session = Depends(get_db)):
    """List all products in the catalog."""
    query = db.query(Product)
    if active_only:
        query = query.filter(Product.active == True)
    products = query.all()
    return [ProductResponse.from_orm_with_price(p) for p in products]


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or not product.active:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductResponse.from_orm_with_price(product)
```

### `backend/app/routers/cart.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cart, Product
from app.schemas import AddToCartRequest, CartResponse, CartItemResponse

router = APIRouter(prefix="/api/cart", tags=["cart"])


def get_session_id(x_session_id: str = Header(None)) -> str:
    """Get or create a session ID from header."""
    return x_session_id or "anonymous"


@router.get("/", response_model=CartResponse)
def get_cart(session_id: str = Depends(get_session_id), db: Session = Depends(get_db)):
    """Get the current cart."""
    items = (
        db.query(Cart)
        .filter(Cart.session_id == session_id)
        .all()
    )
    cart_items = []
    total_cents = 0
    item_count = 0

    for cart_item in items:
        product = cart_item.product
        if not product or not product.active:
            continue
        unit_price = product.price_cents
        total = unit_price * cart_item.quantity
        total_cents += total
        item_count += cart_item.quantity
        cart_items.append(CartItemResponse(
            id=cart_item.id,
            product_id=product.id,
            product_name=product.name,
            quantity=cart_item.quantity,
            unit_price_cents=unit_price,
            total_cents=total,
        ))

    return CartResponse(
        items=cart_items,
        total_cents=total_cents,
        total_dollars=round(total_cents / 100.0, 2),
        item_count=item_count,
    )


@router.post("/add", response_model=CartResponse)
def add_to_cart(
    data: AddToCartRequest,
    session_id: str = Depends(get_session_id),
    db: Session = Depends(get_db),
):
    """Add a product to the cart."""
    product = db.query(Product).filter(Product.id == data.product_id, Product.active == True).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    existing = (
        db.query(Cart)
        .filter(Cart.session_id == session_id, Cart.product_id == data.product_id)
        .first()
    )
    if existing:
        existing.quantity += data.quantity
    else:
        existing = Cart(session_id=session_id, product_id=data.product_id, quantity=data.quantity)
        db.add(existing)
    db.commit()

    return get_cart(session_id, db)


@router.delete("/item/{cart_item_id}", response_model=CartResponse)
def remove_from_cart(
    cart_item_id: int,
    session_id: str = Depends(get_session_id),
    db: Session = Depends(get_db),
):
    """Remove an item from the cart."""
    item = (
        db.query(Cart)
        .filter(Cart.id == cart_item_id, Cart.session_id == session_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    db.delete(item)
    db.commit()
    return get_cart(session_id, db)


@router.delete("/", response_model=dict)
def clear_cart(
    session_id: str = Depends(get_session_id),
    db: Session = Depends(get_db),
):
    """Clear the entire cart."""
    db.query(Cart).filter(Cart.session_id == session_id).delete()
    db.commit()
    return {"message": "Cart cleared"}
```

### `backend/app/routers/checkout.py`

```python
import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cart, Product
from app.schemas import CreateCheckoutRequest, CheckoutResponse
from app.config import STRIPE_SECRET_KEY, FRONTEND_URL

stripe.api_key = STRIPE_SECRET_KEY

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


def get_session_id(x_session_id: str = None) -> str:
    return x_session_id or "anonymous"


@router.post("/create", response_model=CheckoutResponse)
def create_checkout_session(
    data: CreateCheckoutRequest,
    session_id: str = get_session_id(),
    db: Session = Depends(get_db),
):
    """Create a Stripe Checkout session from the current cart."""
    # Get cart items
    cart_items = (
        db.query(Cart)
        .filter(Cart.session_id == session_id)
        .all()
    )
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Build Stripe line items
    line_items = []
    for cart_item in cart_items:
        product = cart_item.product
        if not product or not product.active:
            continue
        if product.stripe_price_id:
            # Use existing Stripe price
            line_items.append({
                "price": product.stripe_price_id,
                "quantity": cart_item.quantity,
            })
        else:
            # Create inline price for this session
            line_items.append({
                "price_data": {
                    "currency": product.currency or "usd",
                    "product_data": {
                        "name": product.name,
                        "description": product.description[:100] if product.description else None,
                    },
                    "unit_amount": product.price_cents,
                },
                "quantity": cart_item.quantity,
            })

    success_url = data.success_url or f"{FRONTEND_URL}/orders/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = data.cancel_url or f"{FRONTEND_URL}/cart"

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=line_items,
            customer_email=data.email or None,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "session_id": session_id,
                "customer_name": data.name or "",
            },
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e.user_message or e}")

    return CheckoutResponse(url=session.url, session_id=session.id)
```

### `backend/app/routers/webhooks.py`

```python
import stripe
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import STRIPE_WEBHOOK_SECRET, STRIPE_SECRET_KEY
from app.models import Cart
from app.services.order import create_order_from_session

stripe.api_key = STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"], include_in_schema=False)


@router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Stripe webhook events.

    Critical events:
      - checkout.session.completed: Payment succeeded, create order
      - checkout.session.expired: Session expired without payment
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Stripe webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except ValueError as e:
        logger.warning(f"Invalid Stripe webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    logger.info(f"Stripe webhook received: {event['type']}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await handle_checkout_completed(session, db)

    elif event["type"] == "checkout.session.expired":
        session = event["data"]["object"]
        logger.info(f"Checkout session expired: {session.get('id')}")

    elif event["type"] == "payment_intent.payment_failed":
        pi = event["data"]["object"]
        logger.warning(f"Payment failed: {pi.get('id')} - {pi.get('last_payment_error', {}).get('message')}")

    return {"status": "received"}


async def handle_checkout_completed(session: dict, db: Session):
    """
    Process a completed checkout session:
    1. Extract customer info from session
    2. Retrieve line items from Stripe
    3. Create order with fulfillment
    4. Clear the cart
    """
    session_id = session.get("id")
    customer_email = session.get("customer_details", {}).get("email", "unknown@example.com")
    customer_name = session.get("customer_details", {}).get("name", "") or session.get("metadata", {}).get("customer_name", "")
    payment_intent = session.get("payment_intent", "")
    cart_session_id = session.get("metadata", {}).get("session_id", "")

    # Retrieve line items from Stripe
    try:
        line_items_data = stripe.checkout.Session.list_line_items(session_id, limit=100)
        line_items = [
            {
                "price_id": item.price.id if hasattr(item, "price") and item.price else None,
                "description": item.description,
                "quantity": item.quantity,
                "amount_total": item.amount_total,
            }
            for item in line_items_data.data
        ]
    except Exception as e:
        logger.error(f"Failed to retrieve line items for session {session_id}: {e}")
        line_items = []

    # Create order
    order = create_order_from_session(
        db=db,
        stripe_session_id=session_id,
        customer_email=customer_email,
        customer_name=customer_name,
        payment_intent=payment_intent,
        line_items=line_items,
    )

    logger.info(f"Order created: #{order.order_number} for {customer_email}")

    # Clear the cart
    if cart_session_id:
        db.query(Cart).filter(Cart.session_id == cart_session_id).delete()
        db.commit()
        logger.info(f"Cart cleared for session: {cart_session_id}")
```

### `backend/app/routers/orders.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order
from app.schemas import OrderResponse

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("/", response_model=list[OrderResponse])
def list_orders(
    email: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List orders, optionally filtered by customer email."""
    query = db.query(Order).order_by(Order.created_at.desc())
    if email:
        query = query.filter(Order.customer_email == email)
    orders = query.limit(limit).all()

    result = []
    for o in orders:
        resp = OrderResponse.model_validate(o)
        resp.total_dollars = round(o.total_cents / 100.0, 2)
        result.append(resp)
    return result


@router.get("/{order_number}", response_model=OrderResponse)
def get_order(order_number: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    resp = OrderResponse.model_validate(order)
    resp.total_dollars = round(order.total_cents / 100.0, 2)
    return resp


@router.post("/{order_number}/cancel", response_model=OrderResponse)
def cancel_order(order_number: str, db: Session = Depends(get_db)):
    """Cancel an order (only if still pending/paid)."""
    from app.models import OrderStatus
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in (OrderStatus.PENDING, OrderStatus.PAID):
        raise HTTPException(status_code=400, detail="Order cannot be cancelled in current status")
    order.status = OrderStatus.CANCELLED
    db.commit()
    db.refresh(order)
    resp = OrderResponse.model_validate(order)
    resp.total_dollars = round(order.total_cents / 100.0, 2)
    return resp
```

### `backend/app/main.py`

```python
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.config import FRONTEND_URL

logging.basicConfig(level=logging.INFO)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="E-Commerce API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Seed products on startup if empty
@app.on_event("startup")
def seed_products():
    from app.database import SessionLocal
    from app.models import Product
    db = SessionLocal()
    if db.query(Product).count() == 0:
        products = [
            Product(name="Classic T-Shirt", description="Comfortable cotton t-shirt", price_cents=2999, active=True),
            Product(name="Wireless Headphones", description="Noise-cancelling Bluetooth headphones", price_cents=9999, active=True),
            Product(name="Coffee Mug", description="Ceramic 12oz mug", price_cents=1499, active=True),
            Product(name="Canvas Backpack", description="Durable canvas backpack with laptop sleeve", price_cents=4999, active=True),
        ]
        db.add_all(products)
        db.commit()
        logging.info("Seeded products")
    db.close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "ecommerce-api"}
```

### `backend/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.35
stripe==10.0.0
psycopg2-binary==2.9.9
```

### `backend/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Stripe Setup

### Test Mode Configuration

1. **Create a Stripe account** at [dashboard.stripe.com](https://dashboard.stripe.com)
2. **Get your API keys** from Developers → API keys
3. **Set up webhook** in Stripe Dashboard → Developers → Webhooks:
   - Endpoint: `https://your-domain.com/api/webhooks/stripe`
   - Events: `checkout.session.completed`, `checkout.session.expired`
   - For local dev: use [Stripe CLI](https://stripe.com/docs/stripe-cli):
     ```bash
     stripe listen --forward-to localhost:8000/api/webhooks/stripe
     ```
4. **Environment variables**:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

## Docker Compose

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: shop
      POSTGRES_PASSWORD: shop
      POSTGRES_DB: shop
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://shop:shop@db:5432/shop
      STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY}
      STRIPE_WEBHOOK_SECRET: ${STRIPE_WEBHOOK_SECRET}
      FRONTEND_URL: http://localhost:5173
    depends_on:
      - db

volumes:
  pgdata:
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/products` | List products |
| GET | `/api/products/:id` | Get product detail |
| GET | `/api/cart` | Get cart (header: `X-Session-ID`) |
| POST | `/api/cart/add` | Add item to cart |
| DELETE | `/api/cart/item/:id` | Remove cart item |
| DELETE | `/api/cart` | Clear cart |
| POST | `/api/checkout/create` | Create Stripe Checkout session |
| POST | `/api/webhooks/stripe` | Stripe webhook (payment confirmation) |
| GET | `/api/orders` | List orders (filter by email) |
| GET | `/api/orders/:number` | Get order detail |
| POST | `/api/orders/:number/cancel` | Cancel order |

## Key Patterns Demonstrated

- **Stripe Checkout integration** — server-side session creation
- **Cart management** — persistent cart with session ID (anonymous)
- **Database price storage** — cents to avoid floating point
- **Webhook processing** — signature verification, event handling
- **Order lifecycle** — pending → paid → processing → shipped → delivered
- **Fulfillment tracking** — email confirmation, extensible for shipping
- **Cart clearing** — automatically on successful payment
- **Product seeding** — startup event for demo data
- **Pydantic computed fields** — `price_dollars` from cents