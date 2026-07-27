# Inner Body JSON Auto-Parse Fix — Design Document

> **BUS-P0-2:** Fix the two-level JSON encoding problem.
> Priority: 🔴 P0. Effort: 2 hours.

## Problem

When sending a structured message, the `body` field is often `json.dumps()`-ed
before passing to `bus_send()`. The outer `bus_read()` auto-parses the PGMQ body
to a dict, but the inner `body` field remains a JSON string. Every consumer must
remember to auto-parse it, leading to:

- Crash: `'str' object has no attribute 'get'` when accessing inner body fields
- Silent data loss: consumer expects a dict, gets a string, comparison fails
- Inconsistent handling: some consumers parse, some don't

## Solution

Fix `bus_send()` and `bus_read()` in `cortex_bus.py` so that the inner body is
auto-serialized (on send) and auto-parsed (on read). Consumers never see JSON strings.

### Send-Side Fix

```python
# In bus_send()
def bus_send(queue, message_body):
    # Auto-serialize inner body if it's a dict
    body_raw = message_body.get("body")
    if isinstance(body_raw, dict):
        message_body["body"] = json.dumps(body_raw)
    # ... rest of send logic unchanged
```

### Read-Side Fix

```python
# In bus_read()
def bus_read(queue, vt=60):
    msg = _api_read(queue, vt)
    if not msg:
        return None
    
    # Auto-parse outer body (existing)
    if isinstance(msg.get("body"), str):
        msg["body"] = json.loads(msg["body"])
    
    # Auto-parse inner body (NEW)
    inner_body = msg["body"].get("body")
    if isinstance(inner_body, str):
        try:
            msg["body"]["body"] = json.loads(inner_body)
        except (json.JSONDecodeError, TypeError):
            pass  # Leave as-is if not valid JSON
    
    return msg
```

### Backward Compatibility

The fix is backward compatible:
- Messages sent with string inner body (old format) are auto-parsed on read
- Messages sent with dict inner body (new format) are auto-serialized on send
- Messages where inner body is a plain string (not JSON) are left as-is
- If inner body is already a dict (read-then-same-agent), no change

### Edge Cases

| Case | Behavior |
|------|----------|
| Inner body is already a dict | No double-serialization (`isinstance` check) |
| Inner body is a string that looks like JSON | Auto-parsed (correct) |
| Inner body is a plain string ("not-json") | Left as-is, no crash |
| Inner body is None | Left as-is |
| Inner body is a number or bool | Left as-is |
| Inner body is a list | Left as-is (unlikely but valid) |

### Files Changed

| File | Action |
|------|--------|
| `ops/scripts/lib/cortex_bus.py` | Modify `bus_send()` and `bus_read()` |

### Verification

```python
# Test: send with dict inner body
bus_send("inbox_moses", {
    "from": "test",
    "subject": "TEST",
    "body": {"key": "value"}  # dict, not string
})

msg = bus_read("inbox_moses", vt=30)
assert isinstance(msg["body"]["body"], dict)
assert msg["body"]["body"]["key"] == "value"
bus_archive("inbox_moses", msg["msg_id"])
```

```python
# Test: backward compat (string inner body)
bus_send("inbox_moses", {
    "from": "test",
    "subject": "TEST",
    "body": json.dumps({"key": "value"})  # old format
})

msg = bus_read("inbox_moses", vt=30)
# Should still auto-parse to dict
assert isinstance(msg["body"]["body"], dict)
assert msg["body"]["body"]["key"] == "value"
bus_archive("inbox_moses", msg["msg_id"])
```
