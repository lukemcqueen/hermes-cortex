---
language: python
tags: [kafka, streaming, queue, events]
title: Kafka Basics
description: Producer/consumer basics with confluent-kafka, topic creation, partitioning, consumer groups, error handling, schema registry
source: pattern
---

# Kafka Basics

## Setup

```python
# pip install confluent-kafka avro-python3
from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic, ConfigResource
import json
import logging

logger = logging.getLogger(__name__)
```

## Admin — Topic Management

```python
def create_topics(broker: str = "localhost:9092"):
    """Create Kafka topics with specific configurations."""
    admin_client = AdminClient({"bootstrap.servers": broker})

    topics = [
        NewTopic(
            topic="user-events",
            num_partitions=6,
            replication_factor=1,  # Use 3 in production
            config={
                "cleanup.policy": "delete",
                "retention.ms": str(7 * 24 * 60 * 60 * 1000),  # 7 days
                "compression.type": "snappy",
            },
        ),
        NewTopic(
            topic="orders",
            num_partitions=10,
            replication_factor=1,
            config={
                "cleanup.policy": "compact",  # Compacted topic — keep latest value per key
                "min.compaction.lag.ms": "60000",
            },
        ),
        NewTopic(
            topic="notifications",
            num_partitions=3,
            replication_factor=1,
            config={
                "cleanup.policy": "delete",
                "retention.ms": str(24 * 60 * 60 * 1000),  # 1 day
            },
        ),
    ]

    # Create topics
    futures = admin_client.create_topics(topics)
    for topic, future in futures.items():
        try:
            future.result()  # Wait for creation
            logger.info(f"Topic '{topic}' created successfully")
        except Exception as e:
            if "TOPIC_ALREADY_EXISTS" in str(e):
                logger.info(f"Topic '{topic}' already exists")
            else:
                logger.error(f"Failed to create topic '{topic}': {e}")


def list_topics(broker: str = "localhost:9092"):
    """List all topics and their partition counts."""
    admin_client = AdminClient({"bootstrap.servers": broker})
    metadata = admin_client.list_topics(timeout=10)

    print("Topics:")
    for topic, metadata in metadata.topics.items():
        if not topic.startswith("_"):  # Skip internal topics
            partitions = len(metadata.partitions)
            print(f"  {topic}: {partitions} partitions")


def describe_topic(broker: str, topic: str):
    """Describe a specific topic's configuration."""
    admin_client = AdminClient({"bootstrap.servers": broker})
    resource = ConfigResource("topic", topic)
    futures = admin_client.describe_configs([resource])

    for res, future in futures.items():
        configs = future.result()
        print(f"Topic: {res.name}")
        for k, v in sorted(configs.items()):
            print(f"  {k}: {v.value}")
```

## Producer

```python
import socket


class KafkaProducer:
    """A reliable Kafka producer with delivery callbacks."""

    def __init__(self, broker: str = "localhost:9092"):
        self.producer = Producer({
            "bootstrap.servers": broker,
            "client.id": f"producer-{socket.gethostname()}",
            "acks": "all",                      # Wait for all replicas to acknowledge
            "compression.type": "snappy",        # Compress messages
            "linger.ms": 5,                      # Batch up to 5ms for higher throughput
            "batch.size": 65536,                 # 64KB batch size
            "retries": 3,                        # Retry on transient errors
            "retry.backoff.ms": 500,             # Wait 500ms between retries
            "enable.idempotence": True,          # Exactly-once semantics
        })

    def delivery_callback(self, err, msg):
        """Called for each produced message to confirm delivery."""
        if err:
            logger.error(f"Failed to deliver message: {err}")
        else:
            logger.debug(
                f"Delivered to {msg.topic()}[{msg.partition()}] "
                f"@ offset {msg.offset()}"
            )

    def produce(self, topic: str, key: str, value: dict):
        """Produce a message to a Kafka topic."""
        try:
            self.producer.produce(
                topic=topic,
                key=key.encode("utf-8") if key else None,
                value=json.dumps(value).encode("utf-8"),
                callback=self.delivery_callback,
            )
            # Trigger delivery reports — non-blocking
            self.producer.poll(0)
        except BufferError:
            logger.warning("Producer queue full, flushing...")
            self.producer.flush()
            self.producer.produce(
                topic=topic,
                key=key.encode("utf-8") if key else None,
                value=json.dumps(value).encode("utf-8"),
                callback=self.delivery_callback,
            )

    def flush(self, timeout: float = 10.0):
        """Flush all pending messages."""
        remaining = self.producer.flush(timeout)
        if remaining > 0:
            logger.warning(f"{remaining} messages pending after flush")
        return remaining


# --- Usage ---
producer = KafkaProducer()

# Produce a user event
producer.produce(
    topic="user-events",
    key="user-123",
    value={
        "event_type": "user_signup",
        "user_id": "123",
        "email": "user@example.com",
        "timestamp": "2024-01-15T10:30:00Z",
    },
)

# Produce an order event (partitioned by order_id)
producer.produce(
    topic="orders",
    key="order-456",  # Same key = same partition = ordered delivery
    value={
        "order_id": "456",
        "user_id": "123",
        "total": 29.99,
        "items": [{"product": "widget", "qty": 2}],
    },
)

producer.flush()


# --- Async produce example ---
def produce_many(topic: str, messages: list[dict]):
    """Produce multiple messages efficiently."""
    producer = KafkaProducer()
    for msg in messages:
        producer.produce(topic, key=msg.get("id"), value=msg)
    producer.flush()
```

## Consumer

```python
class KafkaConsumer:
    """A Kafka consumer with proper error handling and rebalancing."""

    def __init__(self, broker: str, group_id: str, topics: list[str]):
        self.consumer = Consumer({
            "bootstrap.servers": broker,
            "group.id": group_id,
            "client.id": f"consumer-{socket.gethostname()}-{group_id}",
            "auto.offset.reset": "earliest",      # Start from beginning if no offset
            "enable.auto.commit": True,            # Auto-commit offsets
            "auto.commit.interval.ms": 5000,       # Commit every 5 seconds
            "max.poll.interval.ms": 300000,        # Max 5 minutes between polls
            "session.timeout.ms": 45000,           # Consumer considered dead after 45s
            "heartbeat.interval.ms": 3000,         # Send heartbeat every 3s
            "fetch.min.bytes": 1024,               # Wait for at least 1KB of data
            "fetch.max.wait.ms": 500,              # Max 500ms to wait for min bytes
            "max.partition.fetch.bytes": 1048576,  # Max 1MB per partition fetch
        })

        self.consumer.subscribe(topics)

        # Register rebalance listener
        self.consumer.subscribe(
            topics,
            on_assign=self.on_assign,
            on_revoke=self.on_revoke,
        )

    def on_assign(self, consumer, partitions):
        """Called when partitions are assigned (initial assignment or rebalance)."""
        logger.info(f"Assigned partitions: {[p.partition for p in partitions]}")

    def on_revoke(self, consumer, partitions):
        """Called when partitions are revoked (rebalance happening)."""
        logger.info(f"Revoked partitions: {[p.partition for p in partitions]}")
        # Commit offsets before partitions are taken away
        consumer.commit(asynchronous=False)

    def consume(self, timeout: float = 1.0):
        """Poll for messages in a loop with proper shutdown handling."""
        try:
            while True:
                msg = self.consumer.poll(timeout=timeout)

                if msg is None:
                    continue  # No message available, poll again

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition — normal
                        logger.debug(f"End of partition: {msg.topic()}[{msg.partition()}]")
                    elif msg.error().code() == KafkaError._UNKNOWN_TOPIC_OR_PART:
                        raise KafkaException(msg.error())
                    else:
                        raise KafkaException(msg.error())
                else:
                    # Process the message
                    yield self._parse_message(msg)

        except KeyboardInterrupt:
            logger.info("Consumer shutting down...")
        finally:
            self.consumer.close()

    def _parse_message(self, msg):
        """Parse a Kafka message into a dict."""
        return {
            "topic": msg.topic(),
            "partition": msg.partition(),
            "offset": msg.offset(),
            "key": msg.key().decode("utf-8") if msg.key() else None,
            "value": json.loads(msg.value().decode("utf-8")),
            "timestamp": msg.timestamp(),
        }


# --- Consumer with manual offset commit ---
class ManualCommitConsumer:
    """Consumer that manually commits offsets after processing."""

    def __init__(self, broker: str, group_id: str, topics: list[str]):
        self.consumer = Consumer({
            "bootstrap.servers": broker,
            "group.id": group_id,
            "enable.auto.commit": False,  # Manual commit
            "auto.offset.reset": "earliest",
        })
        self.consumer.subscribe(topics)

    def consume_batch(self, batch_size: int = 100, timeout: float = 5.0):
        """Consume a batch of messages, process them, then commit."""
        messages = []
        poll_timeout = timeout / batch_size if batch_size > 0 else timeout

        while len(messages) < batch_size:
            msg = self.consumer.poll(timeout=poll_timeout)
            if msg is None:
                break  # No more messages available
            if msg.error():
                continue
            messages.append(msg)

        if messages:
            # Process batch
            for msg in messages:
                data = {
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                    "value": json.loads(msg.value().decode("utf-8")),
                }
                yield data

            # Commit offsets after successful batch processing
            self.consumer.commit(asynchronous=False)
            logger.info(f"Committed {len(messages)} messages")
```

## Consumer Groups — Multiple Consumers

```python
# --- Consumer group example ---
"""
Consumer groups enable horizontal scaling:

- Each partition is consumed by exactly one consumer in the group
- If you have 6 partitions and 3 consumers, each consumer gets 2 partitions
- If a consumer fails, partitions are rebalanced among remaining consumers
- Add more consumers to increase throughput (up to the number of partitions)
"""

def start_consumer_group(group_id: str, topics: list[str], broker: str = "localhost:9092"):
    """Start a consumer as part of a consumer group."""
    consumer = KafkaConsumer(broker, group_id, topics)
    for message in consumer.consume():
        print(f"Group '{group_id}' received: {message}")
        # Process message...


# Start 3 consumers in the same group for load balancing:
# start_consumer_group("order-processors", ["orders"])
# Run this in 3 separate terminal windows
```

## Error Handling

```python
def consume_with_retry(broker: str, topics: list[str], group_id: str):
    """Consumer with dead-letter queue for failed messages."""
    consumer = Consumer({
        "bootstrap.servers": broker,
        "group.id": group_id,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe(topics)

    # Dead-letter producer
    dlq_producer = Producer({"bootstrap.servers": broker})

    max_retries_per_message = 3

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Consumer error: {msg.error()}")
                continue

            try:
                value = json.loads(msg.value().decode("utf-8"))
                process_message(value)
                consumer.commit(asynchronous=False)

            except Exception as e:
                # Send to dead-letter queue after max retries
                retry_count = msg.headers().get("retry_count", 0) if msg.headers() else 0
                if retry_count >= max_retries_per_message:
                    dlq_producer.produce(
                        topic=f"{msg.topic()}-dead-letter",
                        key=msg.key(),
                        value=msg.value(),
                    )
                    dlq_producer.flush()
                    consumer.commit(asynchronous=False)
                    logger.error(f"Sent to DLQ: {msg.topic()}[{msg.partition()}]@offset {msg.offset()}")
                else:
                    # Re-queue with incremented retry count
                    headers = {"retry_count": str(retry_count + 1)}
                    consumer.commit(asynchronous=False)
                    logger.warning(f"Re-queuing message (retry {retry_count + 1}): {e}")

    finally:
        consumer.close()


def process_message(value: dict):
    """Process a message — raises on failure."""
    if not value.get("data"):
        raise ValueError("Missing data field")
    # Actual processing...
```

## Schema Registry (Avro)

```python
# pip install confluent-kafka[avro]
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField


class AvroKafkaProducer:
    """Producer that uses Avro schemas for serialization."""

    def __init__(self, broker: str, schema_registry_url: str):
        schema_registry = SchemaRegistryClient({"url": schema_registry_url})

        # Define Avro schema
        self.value_schema = """
        {
            "type": "record",
            "name": "UserEvent",
            "namespace": "com.example",
            "fields": [
                {"name": "user_id", "type": "string"},
                {"name": "event_type", "type": "string"},
                {"name": "email", "type": "string"},
                {"name": "timestamp", "type": "string", "default": ""}
            ]
        }
        """

        self.value_serializer = AvroSerializer(
            schema_registry_client=schema_registry,
            schema_str=self.value_schema,
        )

        self.producer = Producer({
            "bootstrap.servers": broker,
            "acks": "all",
        })

    def produce(self, topic: str, key: str, value: dict):
        self.producer.produce(
            topic=topic,
            key=key.encode("utf-8"),
            value=self.value_serializer(
                value,
                SerializationContext(topic, MessageField.VALUE),
            ),
            callback=lambda err, msg: logger.error(f"Delivery failed: {err}") if err else None,
        )
        self.producer.poll(0)
```

## Running Commands

```python
"""
# Docker Compose for local Kafka development:
version: '3'
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:latest
    depends_on: [zookeeper]
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1

  schema-registry:
    image: confluentinc/cp-schema-registry:latest
    depends_on: [kafka]
    ports:
      - "8081:8081"
    environment:
      SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: PLAINTEXT://kafka:9092
      SCHEMA_REGISTRY_HOST_NAME: schema-registry

# Start:
# docker-compose up -d

# Create a topic manually:
# docker-compose exec kafka kafka-topics --create \
#   --topic test-topic \
#   --partitions 3 \
#   --replication-factor 1 \
#   --bootstrap-server localhost:9092

# Consume from command line:
# docker-compose exec kafka kafka-console-consumer \
#   --topic test-topic \
#   --from-beginning \
#   --bootstrap-server localhost:9092

# Produce from command line:
# docker-compose exec kafka kafka-console-producer \
#   --topic test-topic \
#   --bootstrap-server localhost:9092
"""
```