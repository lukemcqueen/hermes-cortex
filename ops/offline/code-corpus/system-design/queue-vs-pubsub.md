---
title: Queue vs Pub/Sub Patterns
description: When to use queues (Celery, BullMQ) vs pub/sub (Redis Pub/Sub, Kafka), message ordering guarantees, at-least-once vs exactly-once, competing consumers, fan-out vs point-to-point.
language: python
tags: [system-design, queues, pubsub, messaging, architecture]
---

# Queue vs Pub/Sub Patterns

## Overview

Message-oriented middleware falls into two broad categories: **queues** (point-to-point) and **pub/sub** (publish-subscribe). Choosing the right pattern is critical for reliability, ordering, and scalability.

| Criterion | Queue | Pub/Sub |
|-----------|-------|---------|
| **Delivery** | One consumer gets each message | All subscribers get each message |
| **Pattern** | Competing consumers | Fan-out / broadcast |
| **Backlog** | Built-in (messages persist) | Depends on broker (Redis Pub/Sub has no backlog) |
| **Ordering** | FIFO within a queue | Partition-based ordering |
| **Use case** | Task distribution, work scheduling | Event broadcasting, real-time feeds |

---

## Queue Pattern (Point-to-Point)

Each message is delivered to exactly one consumer from a group of competing consumers.

### Celery (Python)

```python
# tasks.py
from celery import Celery

app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

# Task result backend
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
)

@app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_payment(self, payment_id: str, amount: float) -> dict:
    try:
        # Simulate payment processing
        result = _charge_payment(payment_id, amount)
        return {"status": "success", "transaction_id": result["id"]}
    except Exception as exc:
        # Automatic retry with exponential backoff
        raise self.retry(exc=exc, countdown=10 * (2 ** self.request.retries))

# worker.py — run in terminal:
# celery -A tasks worker --concurrency=4 --loglevel=info

# app.py — how to call:
# from tasks import process_payment
# process_payment.delay(payment_id="pay_123", amount=49.99)
```

### Competing Consumers Pattern

Multiple worker processes pull from the same queue. Only one wins each message.

```python
import time
import random
from celery import group, chord

@app.task
def send_email_task(user_email: str, template: str) -> str:
    # Simulate variable-length work
    time.sleep(random.uniform(0.1, 0.5))
    print(f"[WORKER] Sent email to {user_email}")
    return f"sent:{user_email}"

# Parallel fan-out to competing consumers:
# celery -A tasks worker --concurrency=8
# Each worker picks up messages independently

def send_bulk_emails(user_emails: list[str]) -> None:
    job = group(
        send_email_task.s(email, "welcome") for email in user_emails
    )
    result = job.apply_async()
    return result  # Wait for all to complete
```

### BullMQ (Node.js — for comparison)

```javascript
// queue.js
const { Queue, Worker } = require('bullmq');

const emailQueue = new Queue('email', {
  connection: { host: 'localhost', port: 6379 },
  defaultJobOptions: {
    attempts: 3,
    backoff: { type: 'exponential', delay: 2000 },
  },
});

// Add job
await emailQueue.add('send-welcome', { userId: 123, email: 'user@example.com' });

// Process jobs
const worker = new Worker('email', async (job) => {
  const { userId, email } = job.data;
  await sendEmail(email, 'Welcome!');
}, {
  connection: { host: 'localhost', port: 6379 },
  concurrency: 5,
});
```

---

## Pub/Sub Pattern (Fan-Out)

Every message published to a topic/channel is delivered to **all** subscribers.

### Redis Pub/Sub (Simple, no backlog)

```python
import asyncio
import aioredis

# Publisher
async def publish_event(event_type: str, payload: dict) -> None:
    redis = await aioredis.from_url("redis://localhost:6379")
    await redis.publish("events:orders", json.dumps({
        "type": event_type,
        "payload": payload,
        "timestamp": time.time(),
    }))
    await redis.close()

# Subscriber A: Notification Service
async def notification_subscriber() -> None:
    redis = await aioredis.from_url("redis://localhost:6379")
    pubsub = redis.pubsub()
    await pubsub.subscribe("events:orders")
    async for msg in pubsub.listen():
        if msg["type"] != "message":
            continue
        event = json.loads(msg["data"])
        if event["type"] == "order.created":
            await send_push_notification(event["payload"]["user_id"])
    await redis.close()

# Subscriber B: Analytics Service
async def analytics_subscriber() -> None:
    redis = await aioredis.from_url("redis://localhost:6379")
    pubsub = redis.pubsub()
    await pubsub.subscribe("events:orders")
    async for msg in pubsub.listen():
        if msg["type"] != "message":
            continue
        event = json.loads(msg["data"])
        await record_event_to_analytics(event)
    await redis.close()
```

**Warning:** Redis Pub/Sub has **no message persistence** — if a subscriber is disconnected, it misses messages.

### Kafka (Durable, partitioned)

```python
# pip install confluent-kafka

from confluent_kafka import Producer, Consumer, KafkaError
import json

# Producer
def produce_order_event(order_id: str, event_type: str, data: dict) -> None:
    producer = Producer({
        "bootstrap.servers": "localhost:9092",
        "acks": "all",  # Wait for all replicas
    })

    producer.produce(
        topic="orders",
        key=order_id,  # Same key → same partition → ordered delivery
        value=json.dumps({"type": event_type, "data": data}).encode(),
        callback=lambda err, msg: print(f"Delivered {msg.partition()}:{msg.offset()}" if not err else f"Failed: {err}"),
    )
    producer.flush()

# Consumer (single consumer in a group — competing consumers)
def consume_order_events(group_id: str = "payment-service") -> None:
    consumer = Consumer({
        "bootstrap.servers": "localhost:9092",
        "group.id": group_id,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
    })
    consumer.subscribe(["orders"])

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise Exception(msg.error())

            event = json.loads(msg.value().decode())
            print(f"[{group_id}] Processing {event['type']} for order {msg.key().decode()}")
            process_event(event)
    finally:
        consumer.close()

# Multiple consumers with different group_ids → fan-out
# consume_order_events("payment-service")   # Gets all messages
# consume_order_events("notification-service")  # Also gets all messages
```

---

## Message Ordering Guarantees

| Broker | Guarantee | How |
|--------|-----------|-----|
| **Redis Queue** | No ordering guarantees across workers | Messages pulled as workers become free |
| **Celery** | No strict ordering (use `task_acks_late` for fairness) | Redelivers on failure, reordering possible |
| **BullMQ** | FIFO per job type | Staged jobs with delays |
| **Kafka** | Strict order **per partition** | Same key → same partition → ordered |
| **RabbitMQ** | FIFO per queue | Single queue ordering |

### Kafka Ordered Processing

```python
from confluent_kafka import Consumer

# Within a partition, messages are strictly ordered.
# If order matters, ensure same key targets same partition.

consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "order-processor",
    "max.poll.interval.ms": 300000,
    # Process one message at a time to preserve order
    "max.poll.records": 1,
})

consumer.subscribe(["orders"])

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    process(msg)  # Sequential processing preserves per-partition order
```

---

## Delivery Guarantees

### At-Least-Once

Messages are delivered at least once; duplicates are possible.

```python
from celery import Task

class AtLeastOnceTask(Task):
    """Celery default — at-least-once delivery."""

    acks_late = True   # Acknowledge AFTER processing
    reject_on_worker_lost = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # Task will be retried automatically
        pass

# If the worker crashes after processing but before ack,
# the task is redelivered to another worker.
```

### Exactly-Once (Idempotent Consumers)

Make consumers idempotent so at-least-once delivery effectively becomes exactly-once.

```python
import psycopg2
from psycopg2.extras import execute_values

def process_payment_event(event: dict) -> None:
    """Idempotent payment processing using a dedup table."""
    event_id = event["id"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            # Check if already processed (idempotency guard)
            cur.execute(
                "SELECT 1 FROM processed_events WHERE event_id = %s",
                (event_id,)
            )
            if cur.fetchone():
                print(f"[SKIP] Event {event_id} already processed")
                return

            # Process the payment
            cur.execute(
                "UPDATE payments SET status = %s WHERE id = %s",
                (event["status"], event["payment_id"]),
            )

            # Record the event as processed
            cur.execute(
                "INSERT INTO processed_events (event_id, processed_at) VALUES (%s, NOW())",
                (event_id,),
            )

        conn.commit()
```

### Kafka Exactly-Once Semantics

```python
producer = Producer({
    "bootstrap.servers": "localhost:9092",
    "enable.idempotence": True,          # Exactly-once producer semantics
    "acks": "all",
    "max.in.flight.requests.per.connection": 5,
})

consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "exactly-once-processor",
    "isolation.level": "read_committed",  # Only read committed transactions
    "enable.auto.commit": False,
})

# Combined with transactional producers for exactly-once ETL
```

---

## When to Use Which

### Use a Queue When:
- Each task should be processed by exactly one worker
- You need task retries and backpressure
- Work distribution across a pool of workers (competing consumers)
- Result backends and progress tracking needed

**Examples:** Email sending, image processing, payment processing, report generation.

### Use Pub/Sub When:
- Multiple services need to react to the same event
- Real-time fan-out (live feeds, notifications)
- Event-driven architecture / event sourcing
- Decoupled service communication

**Examples:** Order events → {notification, analytics, inventory}. Real-time chat. Log streaming.

### Use Both When:
- An event triggers a workflow that fans out

```python
# 1. Producer publishes event (pub/sub)
await redis.publish("events:order.created", order_id)

# 2. Notification service picks up (pub/sub subscriber)
# 3. Notification service queues individual tasks (queue)
send_email_task.delay(user_email, "order_confirmation")
send_sms_task.delay(phone, "Your order #{} confirmed".format(order_id))
```

---

## Key Takeaways

- **Queues** guarantee each message is consumed **once** by a single consumer.
- **Pub/Sub** broadcasts each message to **all** subscribers.
- **Kafka** combines both: topics + consumer groups (groups = queues, group-less = fan-out).
- **Ordering** requires partition-level guarantees (Kafka) or single-threaded consumers.
- **At-least-once** is the common default; **exactly-once** needs idempotent consumers.
- **Competing consumers** scale queue processing; **fan-out** decouples event producers from consumers.
