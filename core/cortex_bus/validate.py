"""cortex_bus.validate — strict bus message envelope validation.

Enforced at the ingestion boundary (``/api/pgmq/send``) so malformed,
spoofed, or oversized messages never enter a queue. Senders receive HTTP 400
with the specific reasons. Strict formatting is the anti-poisoning / anti-spam
posture for a bus with thousands of agents (Luke directive 2026-09-02):

- envelope keys are an allowlist (unknown fields rejected)
- ``from`` must match the authenticated agent (no spoofing)
- subjects are UPPER_CASE protocol names (e.g. EXEC, EXEC_RESULT, PING)
- serialized envelope is capped at 64 KiB
"""

from __future__ import annotations

import json
import re

MAX_MESSAGE_BYTES = 65_536          # 64 KiB serialized envelope
MAX_QUEUE_LEN = 64
MAX_FROM_LEN = 32
MAX_SUBJECT_LEN = 64
MAX_CORR_ID_LEN = 128

RE_QUEUE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
RE_FROM = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
RE_SUBJECT = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
RE_CORR_ID = re.compile(r"^[A-Za-z0-9._:-]{0,128}$")

# The complete set of fields a message envelope may carry. Anything else is
# rejected — an attacker cannot smuggle extra keys or instructions in.
ENVELOPE_KEYS = {
    "from", "to", "subject", "body", "correlation_id", "timestamp",
    "priority", "type",
}

# Workflow messages use a different schema (agent-worker posts step results
# to this queue without a from/subject envelope).
WORKFLOW_RESULT_KEYS = {
    "workflow_id", "step_id", "status", "result", "error",
    "priority", "correlation_id",
}

RE_TYPE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _validate_envelope(msg: dict, authenticated_from: str) -> list[str]:
    """Validate a protocol-envelope message (inbox / orchestrator queues)."""
    errors: list[str] = []

    unknown = set(msg) - ENVELOPE_KEYS
    if unknown:
        errors.append(
            "unknown envelope field(s): " + ", ".join(sorted(unknown))
        )

    sender = msg.get("from")
    if not isinstance(sender, str) or not RE_FROM.match(sender):
        errors.append("from: required lowercase agent name (a-z0-9_-)")
    elif sender != authenticated_from:
        errors.append(
            f"from '{sender}' does not match authenticated agent "
            f"'{authenticated_from}'"
        )

    dest = msg.get("to")
    if dest is not None and (not isinstance(dest, str) or not RE_FROM.match(dest)):
        errors.append("to: optional lowercase agent name (a-z0-9_-)")

    subject = msg.get("subject")
    if not isinstance(subject, str) or not RE_SUBJECT.match(subject):
        errors.append("subject: required UPPER_CASE protocol name (A-Z0-9_)")

    body = msg.get("body")
    if body is None:
        errors.append("body: required")
    elif not isinstance(body, (dict, str)):
        errors.append("body: must be an object or string")

    corr = msg.get("correlation_id")
    if corr is not None and (
        not isinstance(corr, str)
        or not RE_CORR_ID.match(corr)
        or len(corr) < 1
    ):
        errors.append("correlation_id: optional string (A-Za-z0-9._:-)")

    ts = msg.get("timestamp")
    if ts is not None and not isinstance(ts, str):
        errors.append("timestamp: optional ISO-8601 string")

    mtype = msg.get("type")
    if mtype is not None and (not isinstance(mtype, str) or not RE_TYPE.match(mtype)):
        errors.append("type: optional lowercase type name (a-z0-9_)")

    priority = msg.get("priority")
    if priority is not None and (not isinstance(priority, int) or not (0 <= priority <= 100)):
        errors.append("priority: optional integer 0-100")

    return errors


def _validate_workflow_result(msg: dict, authenticated_from: str) -> list[str]:
    """Validate a workflow_step_result message (agent-worker → router)."""
    errors: list[str] = []

    unknown = set(msg) - WORKFLOW_RESULT_KEYS
    if unknown:
        errors.append(
            "unknown workflow-result field(s): " + ", ".join(sorted(unknown))
        )

    for required in ("workflow_id", "step_id", "status"):
        if not isinstance(msg.get(required), str) or not msg.get(required):
            errors.append(f"{required}: required string")

    status = msg.get("status")
    if status not in (None, "success", "failure", "needs_review", "error"):
        errors.append("status: one of success|failure|needs_review|error")

    result = msg.get("result")
    if result is not None and not isinstance(result, (dict, str)):
        errors.append("result: optional object or string")

    corr = msg.get("correlation_id")
    if corr is not None and (
        not isinstance(corr, str) or not RE_CORR_ID.match(corr) or len(corr) < 1
    ):
        errors.append("correlation_id: optional string (A-Za-z0-9._:-)")

    priority = msg.get("priority")
    if priority is not None and (not isinstance(priority, int) or not (0 <= priority <= 100)):
        errors.append("priority: optional integer 0-100")

    return errors


def validate_envelope(msg: object, authenticated_from: str) -> list[str]:
    """Validate one protocol-envelope message (inbox / orchestrator queues)."""
    if not isinstance(msg, dict):
        return ["message must be a JSON object"]
    return _validate_envelope(msg, authenticated_from)


def validate_send_payload(payload: object, authenticated_from: str):
    """Validate the full ``/api/pgmq/send`` payload.

    Queue-aware: ``workflow_step_result`` messages use the workflow schema
    (agent-worker posts results without a from/subject envelope); all other
    queues use the strict protocol envelope.

    Returns ``(errors, parsed_message)`` — errors is a list of strings
    (empty == valid); parsed_message is the envelope as a dict when the
    ``message`` field was a JSON string (None when it wasn't parseable)."""
    errors: list[str] = []
    parsed_message = None
    if not isinstance(payload, dict):
        return ["payload must be a JSON object"], None

    queue = payload.get("queue", "")
    if not isinstance(queue, str) or not RE_QUEUE.match(queue):
        errors.append(f"queue: invalid name (got {queue!r})")

    message = payload.get("message", {})
    if isinstance(message, str):
        try:
            parsed_message = json.loads(message)
        except json.JSONDecodeError:
            errors.append("message: invalid JSON string")
            return errors, None
    else:
        parsed_message = message

    if not isinstance(parsed_message, dict):
        errors.append("message must be a JSON object")
        return errors, parsed_message

    try:
        size = len(json.dumps(parsed_message, default=str))
    except (TypeError, ValueError):
        size = MAX_MESSAGE_BYTES + 1
    if size > MAX_MESSAGE_BYTES:
        errors.append(
            f"message too large: {size} bytes > {MAX_MESSAGE_BYTES}"
        )

    if queue == "workflow_step_result":
        errors.extend(_validate_workflow_result(parsed_message, authenticated_from))
    else:
        errors.extend(_validate_envelope(parsed_message, authenticated_from))

    priority = payload.get("priority", 0)
    if not isinstance(priority, int) or not (0 <= priority <= 100):
        errors.append("priority: integer 0-100")

    return errors, parsed_message
