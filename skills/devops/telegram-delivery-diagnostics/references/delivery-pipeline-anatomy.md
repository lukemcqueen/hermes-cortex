# Delivery Pipeline Anatomy

Tracing from cron output to Telegram message — detailed code-level reference from the July 8 session.

## Entry: Cron Scheduler (scheduler.py)

When a cron job's LLM produces output:

1. Output is handed to `DeliveryRouter.deliver()` via a gateway future
2. The future has a **60-second timeout**
3. If the future times out **and** the coroutine was already dispatched → "assuming delivered" (can't undo the HTTP request)
4. If the future times out **and** the coroutine was cancelled → falls through to standalone path
5. If the future raises an exception → falls through to standalone path

**Standalone path:** Uses `_send_to_platform()` from `tools/send_message_tool.py` — direct HTTP to Telegram API, no gateway adapter.

**Live adapter path:** Calls `adapter.send()` on the Telegram adapter instance.

### Key code: adapter_ok tracking

```python
# scheduler.py lines 1592-1756

adapter_ok = True

# If live adapter sends succeeds → adapter_ok stays True
# If live adapter send fails/times out → adapter_ok = False → falls to standalone

if adapter_ok:
    logger.info("Job '%s': delivered to %s:%s via live adapter",
                job["id"], platform_name, chat_id)
```

## Telegram Adapter (adapter.py, 411KB)

### send() method (line 3546)

```python
async def send(self, chat_id, content, reply_to=None, metadata=None) -> SendResult:
```

**Flow:**
1. Check `self._bot` is initialized — if not, return `SendResult(success=False, error="Not connected")`
2. Check `self._send_path_degraded` — if True, return `SendResult(success=False, error="send_path_degraded")`
3. Skip whitespace-only content
4. Try `_try_send_rich()` for Markdown fast-path (Bot API 10.1+)
5. Format and chunk: `self.truncate_message(formatted, MAX_MESSAGE_LENGTH=4096, len_fn=utf16_len)`
6. For each chunk, up to 3 retry attempts:
   - Try MarkdownV2 first, fall back to plain text on parse errors
   - On `NetworkError`: retry with exponential backoff (1s, 2s)
   - On `TimedOut` (non-connect): raise immediately (message may have reached Telegram)
   - On pool timeout: drain connections and retry
   - On flood control: wait `retry_after` and retry
7. Return `SendResult(success=True, message_ids=[...])`

### splits_long_messages (line 441)

```python
splits_long_messages = True  # send() chunks via truncate_message(MAX_MESSAGE_LENGTH)
```

Messages are split into chunks of MAX_MESSAGE_LENGTH (4096 utf16 code units).
Each chunk goes through its own `send_message` API call — ALL must succeed for the overall send to succeed.

## Telegram Network Layer (telegram_network.py)

### TelegramFallbackTransport (line 52)

An `httpx.AsyncBaseTransport` that retries requests against fallback IPs while preserving TLS/SNI for `api.telegram.org`.

**Connection ordering:**

```python
attempt_order = [sticky_ip] if sticky_ip else [None]
if sticky_ip:
    attempt_order.append(None)  # retry primary after sticky fails
for ip in self._fallback_ips:
    if ip != sticky_ip:
        attempt_order.append(ip)
```

The `sticky_ip` is set when a fallback IP succeeds. Subsequent requests try the sticky IP first.

**Seed fallback IPs (line 43):**
```python
_SEED_FALLBACK_IPS = ["149.154.166.110", "149.154.167.220"]
```

These can be overridden via the `TELEGRAM_FALLBACK_IPS` env var.

**Transport creation (adapter.py lines 3139-3150):**

TWO independent `TelegramFallbackTransport` instances are created:
1. `request` — for outgoing API calls (sendMessage, etc.)
2. `get_updates_request` — for polling (getUpdates)

Each has its own primary transport, fallback transports, and sticky IP.

### _resolve_system_dns() (line 160)

Uses `socket.getaddrinfo()` to resolve `api.telegram.org` and returns the set of IPs. The `force_ipv4` monkey-patch affects this call.

## Gateway Configuration

### force_ipv4 (hermes_constants.py line 937)

Monkey-patches `socket.getaddrinfo` to prefer `AF_INET` (IPv4) when the caller passes `family=0` (AF_UNSPEC). Falls back to full resolution if no A record exists.

```python
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0:
        try:
            return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        except socket.gaierror:
            return _original_getaddrinfo(host, port, family, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)
```

Applied during:
- Gateway startup (`gateway/run.py` line 1689)
- Cron scheduler init (`cron/scheduler.py` line 2765)

### TELEGRAM_FALLBACK_IPS env var

Read at `gateway/config.py` line 1417:
```python
telegram_fallback_ips = getenv("TELEGRAM_FALLBACK_IPS", "")
if telegram_fallback_ips:
    config.platforms[Platform.TELEGRAM].extra["fallback_ips"] = [
        ip.strip() for ip in telegram_fallback_ips.split(",") if ip.strip()
    ]
```

When set, overrides the seed fallback IPs. Passed to `TelegramFallbackTransport.__init__()` via the adapter's initialization code.

## Timeline: July 8 DNS Flapping Event

| Time (KST) | Event |
|---|---|
| 02:08 | Gateway started |
| 02:35 | Primary DNS fails → sticky fallback IP 149.154.166.110 set |
| 03:22 | Same pattern |
| 03:40 | Same pattern |
| **07:10** | **News brief delivered successfully** (via live adapter) |
| **08:07** | **Upwork scanner delivered successfully** |
| **09:16** | **System brief delivered successfully** |
| 09:41 | BOTH DNS and fallback IP 149.154.166.110 fail — total connectivity loss |
| 10:14-10:15 | Bad Gateway → Timed out → reconnection loop |
| 10:16 | Gateway reconnects to Telegram |
| 10:28 | DNS fails again → back to sticky fallback IP |
| 10:38 | Sticky fallback IP ALSO fails; resetting to primary DNS |
| 10:41 | Fallback IP working again |

Note: All three cron deliveries completed BEFORE the first DNS failure at 09:41. The deliveries went through normally from the system's perspective. The cause of missing deliveries was a Telegram-side transient delivery gap, not a DNS issue.

## Session code references

| Component | File | Key lines |
|-----------|------|-----------|
| Cron scheduler | `~/.hermes/hermes-agent/cron/scheduler.py` | 1588-1790 (delivery flow), 1756 (delivered log) |
| Delivery router | `~/.hermes/hermes-agent/gateway/delivery.py` | 388-553 (_deliver_to_platform) |
| Telegram adapter | `~/.hermes/hermes-agent/plugins/platforms/telegram/adapter.py` | 3546-3840 (send method), 439-441 (split config) |
| Fallback transport | `~/.hermes/hermes-agent/plugins/platforms/telegram/telegram_network.py` | 52-130 (full class) |
| force_ipv4 | `~/.hermes/hermes-agent/hermes_constants.py` | 937-976 |
| Gateway config | `~/.hermes/hermes-agent/gateway/config.py` | 1417-1423 (TELEGRAM_FALLBACK_IPS) |
