#!/usr/bin/env python3
"""orch-bus-agent-response-test.py — Agent response test for orchestrators.

no_agent watchdog pattern:
  Empty stdout → silent (no state change)
  Text output  → delivered (new issues or resolutions)

Pings every fleet agent via bus and measures:
  1. Queue depth per agent inbox (are they consuming?)
  2. PING → PONG response time and rate
  3. Response history over multiple runs

State tracked in ~/.hermes-cortex/state/agent-response-state.json for change detection.

Cron: */30 * * * *
"""

import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
STATE_DIR = HOME / ".hermes-cortex" / "state"
STATE_FILE = STATE_DIR / "agent-response-state.json"
REGISTRY_PATH = HOME / ".hermes-cortex" / "state" / "agent-registry.json"
BUS_HEALTH_FILE = STATE_DIR / "agent-response-bus-health.json"

# Timeouts
PING_WAIT = 300   # 5 min to wait for PONG responses
PING_TTL = 3600   # Don't re-ping an agent that was tested within 1 hour

# Track response rate windows
HISTORY_MAX = 100  # max entries per agent
ALERT_THRESHOLD = 0.5  # alert if response rate drops below 50%


def get_agents() -> list[dict]:
    """Load agents from registry, excluding ourselves."""
    agents = []
    if not REGISTRY_PATH.exists():
        return agents
    try:
        data = json.loads(REGISTRY_PATH.read_text())
        for key, val in data.get("agents", {}).items():
            if key == os.environ.get("AGENT_NAME", "moses"):
                continue
            # Skip dev-agents (Titus) — they push only, don't receive bus messages
            if val.get("capabilities", {}).get("bus_mode") == "push_only":
                continue
            agents.append({
                "key": key,
                "name": val.get("name", key),
                "inbox_user": val.get("inbox_user", key),
                "bus_mode": val.get("capabilities", {}).get("bus_mode", "poll"),
            })
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return agents


def bus_send(queue: str, body: dict) -> bool:
    """Send a message to the bus. Returns True on success."""
    try:
        from lib.cortex_bus import bus_send as _send
        result = _send(queue, body)
        return result is not None
    except Exception:
        return False


def bus_read(queue: str, vt: int = 60):
    """Read one message from the bus."""
    try:
        from lib.cortex_bus import bus_read as _read
        return _read(queue, vt)
    except Exception:
        return None


def bus_list_queues() -> list[dict]:
    """List all bus queues with their depths."""
    try:
        from lib.cortex_bus import bus_list_queues as _list
        return _list()
    except Exception:
        return []


def get_queue_depth(queue_name: str, queues: list[dict]) -> int:
    """Get the depth of a specific queue from the queue list."""
    for q in queues:
        if q.get("name") == queue_name:
            return q.get("depth", 0) or q.get("message_count", 0)
    return -1


def load_state() -> dict:
    """Load previous state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "version": 1,
        "agents": {},
        "last_run": None,
        "total_pings_sent": 0,
        "total_pongs_received": 0,
    }


def save_state(state: dict):
    """Save current state."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def main():
    state = load_state()
    agents = get_agents()
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    now_iso = now.isoformat()

    if not agents:
        print("⚠️  No fleet agents found in registry")
        sys.exit(0)

    # ── Step 1: Check bus health ──
    try:
        from lib.cortex_bus import bus_health as _health
        bus_health = _health()
    except Exception:
        bus_health = {"status": "unreachable"}

    bus_up = bus_health.get("status") != "unreachable"
    # Save bus health for cross-reference
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    BUS_HEALTH_FILE.write_text(json.dumps({
        "timestamp": now_iso,
        "status": bus_health.get("status"),
    }))

    if not bus_up:
        # Bus is down — don't spam output, just flag it
        prev_bus = json.loads(BUS_HEALTH_FILE.read_text()) if BUS_HEALTH_FILE.exists() else {}
        if prev_bus.get("status") != "unreachable":
            print("🔴 Bus API unreachable — cannot test agent responses")
        # But still check queue data (might work independently)
        queues = bus_list_queues()
    else:
        queues = bus_list_queues()

    # ── Step 2: Measure queue depths per agent inbox ──
    queue_depths = {}
    for agent in agents:
        inbox = f"inbox_{agent['inbox_user']}"
        depth = get_queue_depth(inbox, queues)
        if depth >= 0:
            queue_depths[agent["key"]] = depth

    # ── Step 3: Check for PONG responses ──
    # Look in inbox_moses for any PONG messages
    pongs_received = []  # agent_key -> response info
    pong_to_check = 5  # check up to 5 messages
    for _ in range(pong_to_check):
        msg = bus_read("inbox_moses", vt=5)
        if not msg:
            break
        body = msg.get("body", {})
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}
        if isinstance(body, dict) and body.get("subject") == "PONG":
            agent_from = body.get("from", "?")
            corr_id = body.get("correlation_id", "")
            ping_id = body.get("body", {}).get("ping_id", "") if isinstance(body.get("body"), dict) else ""
            pongs_received.append({
                "agent": agent_from,
                "correlation_id": corr_id,
                "ping_id": ping_id,
                "timestamp": now_iso,
                "msg_id": msg.get("msg_id", ""),
            })
            # Archive the PONG so it doesn't pile up
            try:
                from lib.cortex_bus import bus_archive
                mid = msg.get("msg_id") or ""
                if mid:
                    bus_archive("inbox_moses", mid)
            except Exception:
                pass

    # ── Step 4: Record pongs in state ──
    for pong in pongs_received:
        agent_key = pong["agent"]
        if agent_key not in state["agents"]:
            state["agents"][agent_key] = {
                "first_seen": now_iso,
                "pongs": [],
                "last_ping_sent": None,
                "last_pong_time": None,
                "queue_depth_history": [],
                "consecutive_misses": 0,
                "consecutive_hits": 0,
            }
        agent_state = state["agents"][agent_key]
        agent_state["pongs"].append({
            "time": now_iso,
            "correlation_id": pong["correlation_id"],
            "ping_id": pong["ping_id"],
        })
        # Trim history
        agent_state["pongs"] = agent_state["pongs"][-HISTORY_MAX:]
        agent_state["last_pong_time"] = now_iso
        agent_state["consecutive_misses"] = 0
        agent_state["consecutive_hits"] = min(agent_state["consecutive_hits"] + 1, 100)
        state["total_pongs_received"] += 1

    # ── Step 5: Send PINGs to agents that are due ──
    pings_sent = 0
    for agent in agents:
        key = agent["key"]
        if key not in state["agents"]:
            state["agents"][key] = {
                "first_seen": now_iso,
                "pongs": [],
                "last_ping_sent": None,
                "last_pong_time": None,
                "queue_depth_history": [],
                "consecutive_misses": 0,
                "consecutive_hits": 0,
            }
        agent_state = state["agents"][key]

        # Check if agent is due for a ping
        last_ping = agent_state.get("last_ping_sent")
        if last_ping:
            last_ping_ts = datetime.fromisoformat(last_ping).timestamp() if isinstance(last_ping, str) else last_ping
            if now_ts - last_ping_ts < PING_TTL:
                continue  # Not due yet

        if not bus_up:
            continue  # Can't send without bus

        corr_id = f"ping-{uuid.uuid4().hex[:12]}"
        ping_id = f"{now_ts:.0f}-{key}"

        # Send PING to the agent's inbox
        success = bus_send(f"inbox_{agent['inbox_user']}", {
            "from": os.environ.get("AGENT_NAME", "moses"),
            "to": key,
            "topic": "fleet",
            "subject": "PING",
            "correlation_id": corr_id,
            "body": {
                "ping_id": ping_id,
                "timestamp": now_iso,
                "expected_response": "PONG",
                "respond_to_queue": "inbox_moses",
                "ttl_seconds": PING_WAIT,
            },
        })

        if success:
            agent_state["last_ping_sent"] = now_iso
            agent_state["last_ping_corr"] = corr_id
            agent_state["last_ping_id"] = ping_id
            pings_sent += 1

    # ── Step 6: Record queue depths ──
    for agent_key, depth in queue_depths.items():
        if agent_key in state["agents"]:
            if "queue_depth_history" not in state["agents"][agent_key]:
                state["agents"][agent_key]["queue_depth_history"] = []
            state["agents"][agent_key]["queue_depth_history"].append({
                "time": now_iso,
                "depth": depth,
            })
            # Trim
            state["agents"][agent_key]["queue_depth_history"] = \
                state["agents"][agent_key]["queue_depth_history"][-HISTORY_MAX:]

    # ── Step 7: Calculate per-agent metrics ──
    alerts = []
    resolutions = []

    for agent in agents:
        key = agent["key"]
        if key not in state["agents"]:
            continue
        agent_state = state["agents"][key]

        # Count recent pongs (last 24 hours)
        pongs = agent_state.get("pongs", [])
        recent_pongs = [p for p in pongs if isinstance(p, dict) and "time" in p]
        # Count pongs within last 24h
        one_day_ago = now_iso[:10]  # just compare date for simplicity
        # More precise: 86400 seconds
        recent_pongs_24h = [
            p for p in recent_pongs
            if isinstance(p.get("time"), str)
            and (now_ts - datetime.fromisoformat(p["time"]).timestamp()) < 86400
        ]

        # Calculate response rate
        pings_sent_count = 0
        pongs_received_count = len(recent_pongs_24h)

        # Estimate pings sent in last 24h (every PING_TTL)
        if agent_state.get("last_ping_sent"):
            last_ping_ts = agent_state.get("last_ping_sent", now_iso)
            if isinstance(last_ping_ts, str):
                last_ping_dt = datetime.fromisoformat(last_ping_ts)
                hours_since_first = min(24, (now_ts - last_ping_dt.timestamp()) / 3600)
            else:
                hours_since_first = 0
            pings_sent_count = max(1, int(hours_since_first * 3600 / PING_TTL))

        response_rate = pongs_received_count / max(pings_sent_count, 1)

        # Consecutive misses tracking
        # If agent was pinged and we have no recent pong, increment misses
        last_ping = agent_state.get("last_ping_sent")
        last_pong = agent_state.get("last_pong_time")
        had_ping_recently = False
        had_pong_recently = False

        if last_ping:
            if isinstance(last_ping, str):
                last_ping_ts = datetime.fromisoformat(last_ping).timestamp()
            else:
                last_ping_ts = float(last_ping)
            if now_ts - last_ping_ts < PING_TTL:  # ping was sent in this window
                had_ping_recently = True

        if last_pong:
            if isinstance(last_pong, str):
                last_pong_ts = datetime.fromisoformat(last_pong).timestamp()
            else:
                last_pong_ts = float(last_pong)
            if now_ts - last_pong_ts < PING_WAIT:  # pong was received recently
                had_pong_recently = True

        # Check for message in the pongs_received list from this run
        got_pong_this_run = any(p["agent"] == key for p in pongs_received)

        if had_ping_recently and not got_pong_this_run:
            agent_state["consecutive_misses"] = agent_state.get("consecutive_misses", 0) + 1
        elif got_pong_this_run:
            agent_state["consecutive_misses"] = 0
            agent_state["consecutive_hits"] = min(agent_state.get("consecutive_hits", 0) + 1, 100)

        # ── Queue depth alerting ──
        recent_depths = agent_state.get("queue_depth_history", [])[-5:]
        if len(recent_depths) >= 3:
            # Check if queue is growing
            depths = [d.get("depth", 0) for d in recent_depths]
            if all(d > 3 for d in depths) and depths[-1] > depths[0]:
                agent_state["queue_growing"] = True
            else:
                agent_state["queue_growing"] = False

    # ── Step 8: Compare with previous state for change detection ──
    output_lines = []
    ts_str = now.strftime("%Y-%m-%d %H:%M UTC")

    for agent in agents:
        key = agent["key"]
        if key not in state["agents"]:
            continue
        agent_state = state["agents"][key]
        name = agent["name"]

        # Check for new silent agents (missed 3+ consecutive pings)
        consecutive = agent_state.get("consecutive_misses", 0)

        # Get previous consecutive misses from state
        prev_misses = 0
        if "prev_consecutive_misses" in agent_state:
            prev_misses = agent_state["prev_consecutive_misses"]

        if consecutive >= 3 and prev_misses < 3:
            alerts.append(f"🔴 {name} ({key}) — no PONG response for {consecutive} consecutive checks")
        elif consecutive >= 3 and consecutive % 6 == 0 and consecutive != prev_misses:
            # Periodic reminder every 6 misses (~3 hours)
            alerts.append(f"🔴 {name} ({key}) — still silent after {consecutive} missed checks")
        elif consecutive == 0 and prev_misses >= 3:
            resolutions.append(f"✅ {name} ({key}) — responding again after {prev_misses} missed checks")

        # Save current misses for next comparison
        agent_state["prev_consecutive_misses"] = consecutive

        # Queue growing alert
        if agent_state.get("queue_growing"):
            qd = agent_state.get("queue_depth_history", [])
            if qd:
                current_depth = qd[-1].get("depth", 0)
                agent_state["queue_growing_alerted"] = agent_state.get("queue_growing_alerted", False)
                if not agent_state["queue_growing_alerted"]:
                    alerts.append(f"⚠️  {name} ({key}) — inbox queue growing ({current_depth} messages pending)")
                    agent_state["queue_growing_alerted"] = True
                elif current_depth > 10 and consecutive >= 3:
                    # Escalate: queue growing + no response = critical
                    agent_state["queue_growing_alerted"] = True
        else:
            if agent_state.get("queue_growing_alerted"):
                resolutions.append(f"✅ {name} ({key}) — inbox queue draining normally")
                agent_state["queue_growing_alerted"] = False

    # Also check historically tracked agents not in current registry
    for key in list(state["agents"].keys()):
        if not any(a["key"] == key for a in agents):
            # Agent was removed from registry — archive entry
            if state["agents"][key].get("active", True):
                state["agents"][key]["active"] = False
                state["agents"][key]["removed_at"] = now_iso

    # ── Step 9: Save state ──
    state["last_run"] = now_iso
    state["total_pings_sent"] += pings_sent
    save_state(state)

    # ── Step 10: Output (change detection) ──
    if alerts or resolutions:
        output_lines.append(f"━━━ Agent Response Test — {len(agents)} agents ━━━ [{ts_str}]")

        if alerts:
            output_lines.append(f"\n⚠️  Issues ({len(alerts)}):")
            output_lines.extend(alerts)

        if resolutions:
            output_lines.append(f"\n✅ Resolved:")
            output_lines.extend(resolutions)

        if pings_sent > 0:
            output_lines.append(f"\n📡 PINGs sent: {pings_sent}")
        if pongs_received:
            output_lines.append(f"📨 PONGs received this tick: {len(pongs_received)}")

        # Quick health summary
        total_agents = len(agents)
        silent = sum(1 for a in agents if state["agents"].get(a["key"], {}).get("consecutive_misses", 0) >= 3)
        healthy = total_agents - silent
        output_lines.append(f"\n📊 Health: {healthy}/{total_agents} agents responding")

        print("\n".join(output_lines))


if __name__ == "__main__":
    main()
