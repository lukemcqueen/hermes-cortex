---
language: python
tags: [celery, queues, async, tasks, python]
title: Celery Tasks
description: Task definition, async execution, result backend (Redis), periodic tasks (celery beat), task routing, error handling
source: pattern
---

# Celery Tasks

## Setup

```python
# pip install celery[redis]
from celery import Celery
from celery.signals import task_failure, task_success
import logging

logger = logging.getLogger(__name__)

# Initialize Celery app with Redis as both broker and result backend
app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

# Optional: Load config from a module
app.config_from_object("celeryconfig")
```

## Configuration (celeryconfig.py)

```python
# celeryconfig.py
from celery.schedules import crontab

# Broker settings
broker_url = "redis://localhost:6379/0"
result_backend = "redis://localhost:6379/1"

# Serialization
task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]
timezone = "UTC"
enable_utc = True

# Task settings
task_track_started = True      # Track task started state
task_time_limit = 300          # Hard time limit (seconds)
task_soft_time_limit = 240     # Soft time limit (seconds)
task_acks_late = True          # Acknowledge after task completes
task_reject_on_worker_lost = True  # Requeue if worker dies
task_default_rate_limit = "100/m"  # Max 100 tasks per minute

# Result settings
result_expires = 3600 * 24 * 7  # Results expire after 7 days

# Routing
task_default_queue = "default"
task_queues = {
    "default": {"exchange": "default", "routing_key": "default"},
    "high_priority": {"exchange": "high_priority", "routing_key": "high_priority"},
    "email": {"exchange": "email", "routing_key": "email"},
    "batch": {"exchange": "batch", "routing_key": "batch"},
}

# Task routes (map task names to queues)
task_routes = {
    "tasks.email.*": {"queue": "email"},
    "tasks.batch.*": {"queue": "batch"},
    "tasks.critical.*": {"queue": "high_priority"},
}

# Periodic tasks (Celery Beat schedule)
beat_schedule = {
    "cleanup-old-records": {
        "task": "tasks.maintenance.cleanup_old_records",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
    },
    "send-daily-digest": {
        "task": "tasks.email.send_daily_digest",
        "schedule": crontab(hour=8, minute=0),  # Daily at 8 AM
    },
    "health-check": {
        "task": "tasks.monitoring.health_check",
        "schedule": 300.0,  # Every 5 minutes
    },
    "sync-external-data": {
        "task": "tasks.batch.sync_external_data",
        "schedule": crontab(hour="*/6", minute=0),  # Every 6 hours
    },
}
```

## Task Definition

```python
from celery import shared_task
from typing import Optional
import time


# --- Basic Task ---
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email(self, user_email: str, user_name: str):
    """
    Send a welcome email to a new user.
    Retries up to 3 times with 60-second delay on failure.
    """
    logger.info(f"Sending welcome email to {user_email}")

    try:
        # Simulate email sending
        # email_client.send(to=user_email, template="welcome", name=user_name)
        time.sleep(1)
        logger.info(f"Welcome email sent to {user_email}")
        return {"status": "sent", "email": user_email}

    except Exception as exc:
        logger.error(f"Failed to send email to {user_email}: {exc}")
        # Retry with exponential backoff
        countdown = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
        raise self.retry(exc=exc, countdown=countdown)


# --- Task with custom binding ---
@shared_task(bind=True)
def process_image(self, image_path: str, transformations: Optional[dict] = None):
    """
    Process an image asynchronously.
    Uses bind=True to access task instance (self).
    """
    self.update_state(state="PROCESSING", meta={"image": image_path, "progress": 0})

    try:
        # Step 1: Load image
        self.update_state(state="PROCESSING", meta={"progress": 25})
        # image = load_image(image_path)

        # Step 2: Apply transformations
        self.update_state(state="PROCESSING", meta={"progress": 50})
        # if transformations:
        #     image = apply_transformations(image, transformations)

        # Step 3: Save result
        self.update_state(state="PROCESSING", meta={"progress": 75})
        # output_path = save_image(image, image_path)

        self.update_state(state="PROCESSING", meta={"progress": 100})
        return {"status": "completed", "output_path": image_path}

    except Exception as exc:
        self.update_state(state="FAILED", meta={"error": str(exc)})
        raise


# --- Group / Chain tasks ---
@shared_task
def add(x: int, y: int) -> int:
    """Simple arithmetic task for demonstrating chains."""
    return x + y


@shared_task
def multiply(x: int, y: int) -> int:
    return x * y


@shared_task
def format_result(result: int) -> str:
    return f"Result: {result}"
```

## Async Execution

```python
from celery import group, chain, chord
from tasks import send_welcome_email, process_image, add, multiply, format_result


# --- Simple async execution ---
def register_user(email: str, name: str):
    """Register a user and send welcome email in background."""
    # Synchronous DB work
    # user = db.create_user(email=email, name=name)

    # Fire-and-forget async task
    result = send_welcome_email.delay(email, name)

    # Return task ID for polling
    return {"user_id": 1, "task_id": result.id}


# --- Get task result ---
def check_email_status(task_id: str):
    """Check the status of a sent email task."""
    result = send_welcome_email.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,      # PENDING, STARTED, SUCCESS, FAILURE, RETRY
        "result": result.result,
        "traceback": result.traceback if result.failed() else None,
    }


# --- Execute with delay vs apply_async ---
def task_execution_examples():
    # Fire and forget (uses default queue)
    send_welcome_email.delay("user@example.com", "Alice")

    # With custom options
    send_welcome_email.apply_async(
        args=["user@example.com", "Bob"],
        queue="email",                 # Route to specific queue
        priority=5,                    # 0-9, higher = more important
        countdown=10,                  # Execute in 10 seconds
        expires=3600,                  # Expire after 1 hour
        retry=True,
    )

    # With ETA
    from datetime import datetime, timedelta
    send_welcome_email.apply_async(
        args=["user@example.com", "Charlie"],
        eta=datetime.utcnow() + timedelta(hours=1),
    )


# --- Task Chains ---
def run_chain():
    """Chain tasks: add → multiply → format_result"""
    # Tasks execute sequentially: 2+3=5, 5*4=20, format→"Result: 20"
    result = chain(
        add.s(2, 3),
        multiply.s(4),
        format_result.s()
    )()

    # Or use the | operator
    result = (add.s(2, 3) | multiply.s(4) | format_result.s())()
    return result.get()  # "Result: 20"


# --- Task Groups (parallel execution) ---
def run_group():
    """Run tasks in parallel."""
    # All three emails sent simultaneously
    job = group(
        send_welcome_email.s("alice@example.com", "Alice"),
        send_welcome_email.s("bob@example.com", "Bob"),
        send_welcome_email.s("charlie@example.com", "Charlie"),
    )
    result = job.apply_async()
    return result  # Wait for all: result.get()


# --- Chord (group + callback) ---
def run_chord():
    """Run tasks in parallel, then execute a callback with all results."""

    @shared_task
    def process_results(results):
        """Callback receives list of individual task results."""
        total = sum(r for r in results)
        return f"Sum of all results: {total}"

    # Run add tasks in parallel, then process_results with the collected outputs
    callback = chord(
        [add.s(i, i) for i in range(10)],  # 0, 2, 4, 6, 8, 10, 12, 14, 16, 18
        body=process_results.s(),
    )
    result = callback()
    return result.get()  # "Sum of all results: 90"
```

## Periodic Tasks (Celery Beat)

```python
# --- Periodic task definitions ---
@shared_task
def cleanup_old_records():
    """Daily cleanup of old database records."""
    logger.info("Cleaning up old records...")
    # db.delete_old_records(days=90)


@shared_task
def send_daily_digest():
    """Send daily email digest to users."""
    logger.info("Generating daily digest...")
    # users = db.get_active_users()
    # for user in users:
    #     generate_and_send_digest.delay(user.id)


@shared_task
def health_check():
    """Periodic health check."""
    logger.info("Health check OK")


# --- Dynamic schedule (add at runtime) ---
def add_periodic_task():
    """Add a periodic task at runtime (requires beat scheduler update)."""
    app.conf.beat_schedule["clean-expired-sessions"] = {
        "task": "tasks.maintenance.cleanup_expired_sessions",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "args": (30,),  # Expire sessions older than 30 days
    }


# --- Running celery beat ---
"""
# Start worker (foreground):
celery -A tasks worker --loglevel=info

# Start worker with concurrency:
celery -A tasks worker --loglevel=info --concurrency=4

# Start beat scheduler:
celery -A tasks beat --loglevel=info

# Start both worker + beat together:
celery -A tasks worker --beat --loglevel=info

# Start specific queues:
celery -A tasks worker -Q email,high_priority --loglevel=info

# Purge all pending tasks:
celery -A tasks purge
"""
```

## Task Routing

```python
# --- Route tasks to specific queues ---
@shared_task(queue="email")
def send_password_reset(email: str, token: str):
    """This task is automatically routed to the 'email' queue."""
    logger.info(f"Sending password reset to {email}")
    # email_client.send_reset(email, token)


@shared_task(queue="high_priority")
def critical_notification(user_id: int, message: str):
    """This task goes to the high-priority queue."""
    logger.info(f"Sending critical notification to user {user_id}")


# --- Manual routing (override queue config) ---
def route_manually():
    send_welcome_email.apply_async(
        args=["user@example.com", "Dave"],
        routing_key="high_priority",
        exchange="high_priority",
    )
```

## Error Handling

```python
from celery import Task
from functools import wraps


# --- Custom Task class with error handling ---
class MonitoredTask(Task):
    """Base task class with automatic error logging and monitoring."""

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when the task fails."""
        logger.error(f"Task {self.name}[{task_id}] failed: {exc}")
        logger.error(f"Args: {args}, Kwargs: {kwargs}")
        logger.error(f"Traceback: {einfo}")

        # Send alert to monitoring system
        # send_alert_to_monitoring(
        #     task_name=self.name,
        #     task_id=task_id,
        #     error=str(exc),
        #     args=args,
        # )

    def on_success(self, retval, task_id, args, kwargs):
        """Called when the task succeeds."""
        logger.info(f"Task {self.name}[{task_id}] succeeded")


# --- Task with retry logic ---
@shared_task(bind=True, base=MonitoredTask, max_retries=5)
def unreliable_operation(self, data: dict):
    """
    Task with exponential backoff retry and max 5 attempts.
    """
    try:
        # Simulate operation that may fail
        result = process_data(data)
        return result

    except ConnectionError as exc:
        # Network issues — retry with exponential backoff
        countdown = 30 * (2 ** self.request.retries)
        logger.warning(f"Connection error, retrying in {countdown}s: {exc}")
        raise self.retry(exc=exc, countdown=countdown)

    except ValueError as exc:
        # Data validation error — don't retry, just fail
        logger.error(f"Invalid data, not retrying: {exc}")
        raise  # Will not retry

    except Exception as exc:
        # Unexpected errors — retry a few times
        if self.request.retries < 3:
            raise self.retry(exc=exc, countdown=60)
        raise


# --- Signal-based monitoring ---
@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Global handler for all task failures."""
    logger.critical(f"Task {sender.name}[{task_id}] failed: {exception}")
    # Notify on-call engineer, increment metrics counter, etc.


# --- Rate-limited task ---
@shared_task(rate_limit="10/m")  # Max 10 executions per minute
def rate_limited_task():
    """This task cannot exceed 10 executions per minute."""
    pass
```