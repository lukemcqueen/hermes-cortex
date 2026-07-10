---
language: python
tags: [redis, queue, pub-sub, cache]
title: Redis as a Queue
description: LPUSH/BRPOP for simple queues, Redis Streams, BullMQ for Node, pub/sub for real-time, connection pooling
source: pattern
---

# Redis as a Queue

## Connection Setup

```python
# pip install redis[hiredis]
import redis.asyncio as aioredis
import json
import asyncio
import logging
from typing import Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class RedisPool:
    """Redis connection pool manager with retry logic."""

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        max_connections: int = 10,
        decode_responses: bool = True,
    ):
        self.url = url
        self.decode_responses = decode_responses
        self.pool = aioredis.ConnectionPool.from_url(
            url,
            max_connections=max_connections,
            decode_responses=decode_responses,
            socket_keepalive=True,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )

    async def get_connection(self) -> aioredis.Redis:
        """Get a Redis connection from the pool."""
        return aioredis.Redis(connection_pool=self.pool)

    async def close(self):
        """Close all connections in the pool."""
        await self.pool.disconnect()


# Global pool — use across your application
redis_pool = RedisPool()


async def get_redis() -> aioredis.Redis:
    """Get a Redis client from the global pool."""
    return await redis_pool.get_connection()
```

## Simple Queue — LPUSH / BRPOP

```python
class SimpleQueue:
    """
    Simple FIFO queue using Redis Lists.
    - LPUSH adds to the left (head)
    - BRPOP removes from the right (tail) with blocking
    """

    def __init__(self, name: str, redis: Optional[aioredis.Redis] = None):
        self.name = name
        self._redis = redis

    async def redis(self) -> aioredis.Redis:
        if self._redis is None:
            return await get_redis()
        return self._redis

    async def enqueue(self, item: dict):
        """Add an item to the queue."""
        r = await self.redis()
        await r.lpush(self.name, json.dumps(item))
        logger.debug(f"Enqueued to {self.name}: {item.get('id', 'unknown')}")

    async def dequeue(self, timeout: int = 0) -> Optional[dict]:
        """
        Remove and return an item from the queue.
        Blocks until an item is available (timeout=0) or timeout seconds.
        Returns None if timeout reached.
        """
        r = await self.redis()
        result = await r.brpop(self.name, timeout=timeout)
        if result is None:
            return None
        _, value = result  # result is (key, value) tuple
        return json.loads(value)

    async def size(self) -> int:
        """Get the number of items in the queue."""
        r = await self.redis()
        return await r.llen(self.name)

    async def clear(self):
        """Remove all items from the queue."""
        r = await self.redis()
        await r.delete(self.name)


# --- Usage ---
async def simple_queue_example():
    queue = SimpleQueue("email-queue")

    # Enqueue items
    await queue.enqueue({"id": "1", "to": "alice@example.com", "template": "welcome"})
    await queue.enqueue({"id": "2", "to": "bob@example.com", "template": "receipt"})

    print(f"Queue size: {await queue.size()}")  # 2

    # Dequeue items (FIFO order)
    item1 = await queue.dequeue()
    print(f"Dequeued: {item1}")  # {"id": "1", ...}

    item2 = await queue.dequeue()
    print(f"Dequeued: {item2}")  # {"id": "2", ...}


# --- Worker pattern ---
async def simple_worker(queue_name: str):
    """Background worker that processes items from a simple queue."""
    queue = SimpleQueue(queue_name)
    logger.info(f"Worker started for queue: {queue_name}")

    while True:
        try:
            item = await queue.dequeue(timeout=5)
            if item is None:
                continue

            logger.info(f"Processing: {item}")
            # await process_email(item)
            # await save_to_database(item)

        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(1)
```

## Redis Streams

```python
class StreamQueue:
    """
    Redis Streams — a more robust queue with:
    - Message IDs (auto-generated or custom)
    - Consumer groups for load balancing
    - Acknowledgment-based consumption
    - Message history and replay
    """

    def __init__(self, stream: str, group: Optional[str] = None):
        self.stream = stream
        self.group = group

    async def add(self, fields: dict, maxlen: int = 10000):
        """Add a message to the stream."""
        r = await get_redis()
        message_id = await r.xadd(self.stream, fields, maxlen=maxlen)
        return message_id

    async def create_group(self, group: str, start_id: str = "0"):
        """Create a consumer group. Idempotent."""
        r = await get_redis()
        try:
            await r.xgroup_create(self.stream, group, id=start_id, mkstream=True)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Consumer group '{group}' already exists")
            else:
                raise

    async def read_group(
        self,
        group: str,
        consumer: str,
        count: int = 1,
        block: int = 5000,
    ) -> list[dict]:
        """
        Read messages as a consumer group member.
        Messages are delivered to one consumer per group per stream.
        """
        r = await get_redis()
        results = await r.xreadgroup(
            group,
            consumer,
            {self.stream: ">"},  # ">" = only new messages
            count=count,
            block=block,
        )

        messages = []
        for stream_name, entries in results:
            for message_id, fields in entries:
                messages.append({"id": message_id, **fields})
        return messages

    async def acknowledge(self, group: str, message_id: str):
        """Acknowledge a message as processed."""
        r = await get_redis()
        await r.xack(self.stream, group, message_id)

    async def pending(self, group: str) -> list[dict]:
        """Get pending (unacknowledged) messages."""
        r = await get_redis()
        results = await r.xpending_range(self.stream, group, min="-", max="+", count=100)
        return [{"id": m["message_id"], "consumer": m["consumer"], "times_delivered": m["times_delivered"]} for m in results]

    async def length(self) -> int:
        """Get the stream length."""
        r = await get_redis()
        return await r.xlen(self.stream)

    async def claim_stale(self, group: str, consumer: str, min_idle_time_ms: int = 60000):
        """
        Claim pending messages from failed consumers.
        Messages idle for longer than min_idle_time_ms are reassigned.
        """
        r = await get_redis()
        pending = await r.xpending_range(
            self.stream, group, min="-", max="+", count=100
        )
        stale_ids = [
            m["message_id"]
            for m in pending
            if m["times_delivered"] > 0 and (
                # Approximate idle check — in production compare timestamps
                True
            )
        ]
        if stale_ids:
            claimed = await r.xclaim(
                self.stream, group, consumer, min_idle_time_ms, stale_ids
            )
            return claimed
        return []


# --- Stream worker with consumer group ---
async def stream_worker(stream: str, group: str, consumer: str):
    """Worker that consumes from a stream using consumer groups."""
    queue = StreamQueue(stream)
    await queue.create_group(group)

    logger.info(f"Stream worker: {consumer} (group: {group}, stream: {stream})")

    while True:
        try:
            messages = await queue.read_group(group, consumer, count=10, block=2000)
            for msg in messages:
                logger.info(f"Processing: {msg['id']}")
                # Process the message...
                await process_order(msg)
                await queue.acknowledge(group, msg["id"])

        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(1)


async def process_order(msg: dict):
    """Process an order message."""
    # Simulate processing
    await asyncio.sleep(0.1)
    return True
```

## Pub / Sub for Real-Time

```python
class PubSub:
    """
    Redis Pub/Sub — lightweight real-time messaging.
    Messages are fire-and-forget (no persistence, no acknowledgment).
    """

    def __init__(self):
        self._pub = None
        self._sub = None

    async def publish(self, channel: str, message: dict):
        """Publish a message to a channel."""
        if self._pub is None:
            self._pub = await get_redis()
        await self._pub.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str, handler: Callable):
        """
        Subscribe to a channel and call handler for each message.
        Runs until cancelled.
        """
        if self._sub is None:
            self._sub = await get_redis()

        pubsub = self._sub.pubsub()
        await pubsub.subscribe(channel)

        logger.info(f"Subscribed to channel: {channel}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await handler(data)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(channel)
            logger.info(f"Unsubscribed from channel: {channel}")


# --- Pub/Sub usage ---
async def pubsub_example():
    pubsub = PubSub()

    # Start listener in background
    async def handle_notification(data: dict):
        print(f"Got notification: {data}")

    listener = asyncio.create_task(
        pubsub.subscribe("notifications", handle_notification)
    )

    # Publish messages
    await pubsub.publish("notifications", {"type": "new_follower", "user": "alice"})
    await pubsub.publish("notifications", {"type": "like", "post_id": "42"})

    # Let listener process
    await asyncio.sleep(0.1)

    # Clean up
    listener.cancel()
    await listener
```

## BullMQ (Node.js)

```typescript
// --- BullMQ — production-grade queue for Node.js ---
// npm install bullmq ioredis

import { Queue, Worker, QueueScheduler } from 'bullmq';

const connection = {
  host: 'localhost',
  port: 6379,
};

// Define a queue
const emailQueue = new Queue('email', { connection });

// Add jobs
await emailQueue.add('send-welcome', {
  to: 'user@example.com',
  template: 'welcome',
}, {
  attempts: 3,        // Retry up to 3 times
  backoff: {          // Exponential backoff
    type: 'exponential',
    delay: 2000,      // 2s, 4s, 8s
  },
  delay: 0,           // Execute immediately
  removeOnComplete: { age: 3600 * 24 },  // Keep for 24h
  removeOnFail: { age: 3600 * 24 * 7 },  // Keep failed for 7 days
});

// Add a delayed job
await emailQueue.add('send-digest', { userId: '123' }, {
  delay: 24 * 60 * 60 * 1000,  // 24 hours from now
});

// Worker — processes jobs from the queue
const worker = new Worker('email', async (job) => {
  console.log(`Processing job ${job.id}: ${job.name}`);
  const { to, template } = job.data;

  switch (template) {
    case 'welcome':
      // Send welcome email
      break;
    case 'receipt':
      // Send receipt
      break;
  }

  return { success: true, sentTo: to };
}, {
  connection,
  concurrency: 5,        // Process 5 jobs in parallel
  limiter: {
    max: 10,              // Max 10 jobs per...
    duration: 1000,       // ...second
  },
});

worker.on('completed', (job) => {
  console.log(`Job ${job.id} completed`);
});

worker.on('failed', (job, err) => {
  console.error(`Job ${job.id} failed:`, err.message);
});

// Queue scheduler — handles delayed jobs, retries, etc.
const scheduler = new QueueScheduler('email', { connection });

// Scheduled / repeatable jobs
await emailQueue.add('daily-cleanup', {}, {
  repeat: {
    pattern: '0 3 * * *',  // Daily at 3 AM (cron syntax)
  },
});

// Job lifecycle
const job = await emailQueue.add('send-email', { to: 'a@b.com' });
const state = await job.getState();  // 'waiting', 'active', 'completed', 'failed'
const progress = await job.progress; // Custom progress (0-100)
await job.remove();
```

## Comparison Table

```python
"""
┌──────────────────┬──────────────┬───────────────┬──────────────────┬──────────────┐
│ Feature          │ LPUSH/BRPOP  │ Redis Streams │ Pub/Sub          │ BullMQ       │
├──────────────────┼──────────────┼───────────────┼──────────────────┼──────────────┤
│ Persistence      │ Yes          │ Yes           │ No (fire/forget) │ Yes          │
│ Acknowledgment   │ No (pop=done)│ Yes (XACK)    │ No               │ Yes          │
│ Consumer Groups  │ No           │ Yes           │ No               │ Yes          │
│ Delayed Jobs     │ Manual       │ No            │ No               │ Yes          │
│ Scheduled Jobs   │ No           │ No            │ No               │ Yes (cron)   │
│ Message Replay   │ No           │ Yes           │ No               │ No           │
│ Throughput       │ Very High    │ High          │ Very High        │ High         │
│ Complexity       │ Low          │ Medium        │ Low              │ Medium-High  │
│ Best For         │ Simple FIFO  │ Reliable      │ Real-time        │ Production   │
│                  │ task queues  │ event streams │ broadcasts       │ job queues   │
└──────────────────┴──────────────┴───────────────┴──────────────────┴──────────────┘
"""
```

## Complete Worker Example

```python
async def main():
    """Example of using Redis streams for order processing."""
    stream = StreamQueue("orders", "order-processors")

    # Create consumer group
    await stream.create_group("order-processors")

    # Start multiple workers (simulate with asyncio.gather)
    async def worker_1():
        await stream_worker("orders", "order-processors", "worker-1")

    async def worker_2():
        await stream_worker("orders", "order-processors", "worker-2")

    # Run workers concurrently
    await asyncio.gather(worker_1(), worker_2())


# Run with: asyncio.run(main())
```