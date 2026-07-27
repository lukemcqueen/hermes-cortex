---
name: telegram-delivery-diagnostics
description: Diagnose and fix Telegram delivery issues for Hermes cron jobs — delivery pipeline tracing, DNS/network diagnostics, adapter state verification, and known failure patterns.
category: devops
author: Moses
version: 1.0.0
platforms: [linux, macos]
---

# Telegram Delivery Diagnostics

Diagnose why a Hermes cron job's output didn't reach the user on Telegram.

## When to use

- User says "I didn't get my news/brief/alert today"
- Cron job logs `delivered` but user didn't see it
- Gateway.log shows Telegram DNS failures or fallback IP flapping
- After a network outage or DNS resolver change
- When adding a new cron with Telegram delivery target

## Architecture — How Cron Deliveries Work

```
Cron job finishes
  → scheduler.py queues delivery via gateway's event loop (future)
  → DeliveryRouter._deliver_to_platform()
  → Telegram adapter.send()
     → self._bot.send_message() (python-telegram-bot)
        → httpx client with TelegramFallbackTransport
           → Primary DNS: api.telegram.org
           → Fallback: 149.154.166.110, 149.154.167.220
     → 3 retry attempts per chunk on NetworkError
  → Returns SendResult(success=True, message_id=...)
  → Scheduler logs: "delivered to telegram:CHAT_ID via live adapter"
```

### Two delivery paths

| Path | When | Mechanism |
|------|------|-----------|
| **Live adapter** | Default for all crons | Goes through gateway's adapter (`adapter.send()`). Returns success/failure. |
| **Standalone** | Live adapter unavailable or timed out | Direct HTTP to Telegram API via `_send_to_platform()`. Bypasses gateway entirely. |

### Key configuration points

| Layer | What to check | File |
|-------|--------------|------|
| Bot token | `TELEGRAM_BOT_TOKEN` | `~/.hermes/.env` |
| Home channel | `TELEGRAM_HOME_CHANNEL` (should match user chat_id) | `~/.hermes/.env` |
| Allowed users | `TELEGRAM_ALLOWED_USERS` | `~/.hermes/.env` |
| Platform config | `display.platforms.telegram.streaming: true` | `~/.hermes/config.yaml` |
| IPv4 preference | `network.force_ipv4: true` | `~/.hermes/config.yaml` |
| Fallback IPs | `TELEGRAM_FALLBACK_IPS` env var (optional, overrides defaults) | `~/.hermes/.env` or config |
| Cron delivery target | Format: `telegram:CHAT_ID` | Cron job definition |

## Verification checklist

When a user reports missing delivery, run through these in order:

### 1. Check cron ran successfully

```bash
cronjob action='list' --filter <job-name>
# Check: last_status == "ok", last_delivery_error == null
```

### 2. Check delivery log in agent.log

```
grep "<JOB_ID>.*delivered" ~/.hermes/logs/agent.log
# Should say "delivered to telegram:1270130526 via live adapter"
```

### 3. Check gateway delivery log

```bash
grep -a "<JOB_ID>" ~/.hermes/logs/gateway.log
# Should show "Cron output preserved for chunking adapter" if message > 4000 chars
# NO error after this entry means send was successful
```

### 4. Check Telegram API connectivity

```bash
# Test directly (bypasses gateway)
TOKEN=$(grep "^TELEGRAM_BOT_TOKEN=" ~/.hermes/.env | cut -d= -f2-)
curl -s --max-time 10 "https://api.telegram.org/bot${TOKEN}/getMe"
# Expect: {"ok":true,"result":{"id":...,"is_bot":true,...}}

# Test sendMessage
curl -s --max-time 10 -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -d "chat_id=1270130526" -d "text=🧪 Diagnostics test"
```

### 5. Check DNS resolution

```bash
# System DNS
getent hosts api.telegram.org
# Should return an IPv4 address (149.154.166.110)
# If IPv6 (2001:67c:4e8:f004::9) appears, IPv6 may be failing

# Check if force_ipv4 patch is active
python3 -c "
import socket
print('Patched:', getattr(socket.getaddrinfo, '_hermes_ipv4_patched', False))
"

# Full DNS diagnostics
for i in 1 2 3 4 5; do
  dig +short api.telegram.org @192.168.1.1 2>/dev/null
done
# If results are inconsistent → DNS flapping
```

### 6. Check gateway Telegram connection state

```bash
grep -a "Telegram" ~/.hermes/logs/gateway.log | grep "07-08" | tail -10
# Look for: 
# - "sticky fallback IP" → DNS was failing, using fallback
# - "sticky fallback IP failed" → fallback ALSO failed
# - "polling resumed" → recovered
# - "polling reconnect failed" → still down
```

## Known failure patterns

### Pattern A: DNS flapping — systemd-resolved intermittent failures

**Symptom:** `[Errno -2] Name or service not known` in errors.log, followed by automatic fallback IP usage. Cron deliveries may succeed or fail depending on timing.

**Root cause:** System DNS resolver (192.168.1.1 via systemd-resolved) intermittently fails to resolve `api.telegram.org`. The TelegramFallbackTransport handles this by retrying fallback IPs `149.154.166.110`, `149.154.167.220`.

**Impact:** 
- Send path has its OWN transport (separate from polling)
- Each send gets 3 retries with fallback IPs
- During periods when BOTH DNS and fallback IPs fail, sends fail
- The `force_ipv4: true` config can't help when DNS itself is unreachable

**Fix:**
1. (Preferred) Pin IPv4 in `/etc/hosts`:
   ```
   echo "149.154.166.110 api.telegram.org" | sudo tee -a /etc/hosts
   ```
   This bypasses system DNS entirely for `api.telegram.org`.

2. (Already set) Ensure `network.force_ipv4: true` in `~/.hermes/config.yaml`.
   This monkey-patches `socket.getaddrinfo` to prefer `AF_INET` (IPv4) before IPv6.

3. (Belt-and-suspenders) Set `TELEGRAM_FALLBACK_IPS` in `.env` to ensure fallback is always configured.

### Pattern B: IPv6 connectivity failures

**Symptom:** `api.telegram.org` resolves to BOTH `149.154.166.110` (IPv4) and `2001:67c:4e8:f004::9` (IPv6). `ping6` to the IPv6 address fails, but Python's httpx may attempt IPv6 first and time out.

**Diagnosis:**
```bash
ping6 -c1 -W2 2001:67c:4e8:f004::9
# If FAIL → IPv6 is broken on this network
resolvectl query api.telegram.org
# Shows both addresses
```

**Fix:** Same as Pattern A — `/etc/hosts` IPv4 pinning eliminates IPv6 resolution entirely.

### Pattern C: Telegram-side delivery gap (API accepts but doesn't deliver)

**Symptom:** All system logs show successful delivery (adapter.send() returned success, message_ids received), but user reports messages never arrived. This is rare but documented on Telegram's side.

**Diagnosis:** Only diagnosable by exclusion — if all system-side checks pass and the user confirms a test message sent NOW arrives, the earlier messages were likely lost in a Telegram-side transient delivery gap.

**Fix:** No server-side fix. If it happens, note the time and check Telegram status pages.

### Pattern D: Adapter not initialized for cron delivery

**Symptom:** `send_result` is None or "Not connected", cron falls through to standalone path.

**Diagnosis:** Check gateway.log for Telegram adapter initialization errors:
```bash
grep -a "Not connected\|send_path_degraded\|adapter.*failed" ~/.hermes/logs/gateway.log
```

**Fix:** Restart the gateway: `hermes restart`.

### Pattern E: Thread/topic delivery goes to wrong lane

**Symptom:** Private DM topic deliveries end up in the General topic instead of the named thread.

**When it happens:** Cron deliveries with `attach_to_session: true` create named private DM topics. If the topic creation fails or the thread_id is wrong, messages fall through to the wrong lane.

**Fix:** Check `thread_id` in the cron's origin metadata. For regular DM deliveries (no thread), ensure `deliver: telegram:CHAT_ID` has no thread_id component.

## Log reference

### Where to look

| Log | Path | What it tells you |
|-----|------|-------------------|
| Cron scheduler | `~/.hermes/logs/agent.log` | Job ran, delivered status, delivery errors |
| Gateway delivery | `~/.hermes/logs/gateway.log` | Output received, adapter.send() called, Telegram connectivity |
| Errors | `~/.hermes/logs/errors.log` | DNS failures, Telegram network errors, adapter connection issues |

### Key log patterns

**Successful delivery (normal):**
```
INFO gateway.delivery: Cron output preserved for chunking adapter (8050 chars)
INFO cron.scheduler: Job 'JOB_ID': delivered to telegram:1270130526 via live adapter
```

**Successful delivery (small message — under 4000 chars, no chunking):**
```
INFO cron.scheduler: Job 'JOB_ID': delivered to telegram:1270130526 via live adapter
```
(No "Cron output preserved" log — message was small enough to send directly.)

**DNS failure with fallback recovery:**
```
WARNING plugins.platforms.telegram.telegram_network: Primary api.telegram.org connection failed
WARNING plugins.platforms.telegram.telegram_network: ... path unreachable; using sticky fallback IP 149.154.166.110
```

**Total connectivity loss (both DNS and fallback fail):**
```
WARNING plugins.platforms.telegram.telegram_network: Primary api.telegram.org connection failed
WARNING plugins.platforms.telegram.telegram_network: Fallback IP 149.154.166.110 failed
WARNING plugins.platforms.telegram.telegram_network: Sticky fallback IP ... failed; resetting to primary DNS path
```

**Delivery timeout — assumed delivered (in flight):**
```
WARNING cron.scheduler: Job 'JOB_ID': live adapter send to telegram:CHAT_ID timed out after 60s; already dispatched, assuming delivered
```

**Delivery timeout — standalone fallback:**
```
WARNING cron.scheduler: Job 'JOB_ID': live adapter send ... timed out before the coroutine was dispatched, falling back to standalone
```

**Live adapter routine responses to user-initiated messages:**
```
INFO gateway.platforms.base: [Telegram] Sending response (N chars) to CHAT_ID
INFO hermes_plugins.telegram_platform.adapter: [Telegram] Flushing text batch agent:main:telegram:dm:CHAT_ID (N chars)
```

## Pitfalls

- **"Delivered via live adapter" ≠ proof the user saw it.** The log only proves Telegram's API returned a 200. Telegram can accept messages and fail to deliver them to the user's client.
- **gateway.log is a binary file** (contains control characters). Always use `grep -a` when searching it.
- **force_ipv4 doesn't fix all DNS issues.** The monkey-patch prefers IPv4 but can't help when the DNS server itself is unreachable (`[Errno -2]`). Use `/etc/hosts` pinning for that case.
- **Cron deliveries use a different log path than interactive responses.** Interactive messages show `Sending response` in gateway.log. Cron deliveries go through `adapter.send()` directly and don't produce that log line. Don't assume a missing "Sending response" means failure.
- **splits_long_messages = True means long crons are chunked.** The chunking adapter (`splits_long_messages=True`) means messages over 4000 chars are split. Each chunk gets its own `send_message` API call. If one chunk fails after all 3 retries, the ENTIRE send fails.
- **Fallback IPs can also fail.** The seed fallback IPs (149.154.166.110, 149.154.167.220) are stable Telegram Bot API endpoints but can be unreachable from certain geographic regions during network events.
- **Two transports, one adapter.** The Telegram adapter creates TWO `TelegramFallbackTransport` instances — one for requests (sending) and one for get_updates (polling). Each has its own primary transport, fallback transports, and sticky IP. The send path's transport is independent of the polling path's connectivity.
