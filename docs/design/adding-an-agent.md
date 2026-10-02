# Adding an agent to the gateway — it's config, not code

The gateway's `poll → dispatch → reply` loop is agent-agnostic. An agent is a **backend
spec** in `gateway.yaml`; the spec names a **kind**, and a kind is one implementation of the
`BackendAdapter` seam (`ops/scripts/cortex_gateway/backend.py`).

```
human → Telegram → transport → envelope → [ BACKEND ] → reply envelope → transport → human
                                              │
                        kind=hermes  (the bus: inbox_<agent> in, out_<agent> out)
                        kind=command (any CLI coding agent, spawned per turn)
                        kind=<yours> (register_kind — a new protocol, one class)
```

## Add an agent of an existing kind (no code)

```json
"backends": [
  {"name": "esther", "kind": "hermes"},

  {"name": "pi", "kind": "command",
   "command": ["pi", "--model", "openrouter/moonshotai/kimi-k2.6"],
   "prompt_template": "{body}",
   "timeout_s": 300,
   "reply_mode": "sync",
   "capabilities": ["code", "review"],
   "model": "openrouter/moonshotai/kimi-k2.6"}
]
```

Spec fields (`AgentSpec`, `ops/scripts/cortex_gateway/agents.py`):

| field | meaning |
|---|---|
| `name` | the agent name — becomes the queue names `inbox_<name>` / `out_<name>`; must be unique |
| `kind` | `hermes` (bus) · `command` (CLI) · anything you register |
| `command` | kind=command: argv list; the prompt is appended as the final argument |
| `prompt_template` | how the inbound message becomes the prompt: `{body}` `{agent}` `{channel}` `{user}` `{model}` |
| `timeout_s` | per-turn wall clock; a timeout is a logged no-reply, never a crash |
| `reply_mode` | `sync` (return the reply now) · `bus` (write it to `out_<name>`, gateway drains) |
| `capabilities` | free-form, for operators and `health()` — this is what "different functions" looks like |
| `model` | informational, and available to `prompt_template` |
| `subject` | kind=hermes: the UPPER_CASE bus subject for inbound human messages |

## Worked example: a Telegram bot answered by pi (verified live)

```json
"backends": [
  {"name": "pi", "kind": "command",
   "command": ["/home/esther/.pi/agent/bin/pi", "--model", "openrouter/moonshotai/kimi-k2.6"],
   "output": "last_line",
   "timeout_s": 300,
   "reply_mode": "sync",
   "capabilities": ["code", "review"],
   "model": "openrouter/moonshotai/kimi-k2.6"}
],
"bots": [{"token_ref": "TELEGRAM_BOT_TOKEN", "channel": "telegram",
          "routing": {"default": "pi", "overrides": {}}}],
"routing": {"default": "pi", "overrides": {}}
```

Copy: `ops/scripts/gateway-pi.example.yaml`. Three things the live rehearsal taught, all of
which are now spec fields rather than gotchas to rediscover:

- **Absolute path to the binary.** pi's linuxbrew symlink is not on a service PATH; a
  relative command in a systemd context is an agent that answers nothing.
- **`output: last_line`.** pi prints its extension's session line before the answer, so
  `raw` would send `CORTEX_RESUME …` to the human.
- **`timeout_s` sized for a real turn.** A coding turn is not a chat reply.

Verified end to end on a second bot token: the bot's message → the command backend spawned
pi → pi's last line became the reply → Telegram returned `message_id 12`.

## Add a new KIND (one class, one line)

A different protocol (a hosted API, a websocket agent, an agent that answers on a callback
URL) is a class with the four seam methods, plus registration:

```python
from cortex_gateway.agents import register_kind, AgentSpec, reply_from_origin
import gateway_envelope as env

class HttpAgent:
    """An agent reachable over HTTP. dispatch() returns the reply, or None if silent."""
    def __init__(self, spec: AgentSpec, ctx: dict):
        self.spec, self.endpoint = spec, spec.extra.get("endpoint", "")

    def start(self): pass
    def stop(self): pass
    def poll_replies(self, max_n=5): return []          # sync kind
    def health(self): return {"ok": bool(self.endpoint), "backend": "http"}

    def dispatch(self, envelope: dict):
        inbound = env.validate(envelope)
        text = call_my_api(self.endpoint, inbound["body"])     # your transport
        if not text:
            return None                                        # silent turn is legitimate
        return env.validate(reply_from_origin(inbound, text, agent=self.spec.name))

@register_kind("http")
def _build_http(spec, ctx):
    return HttpAgent(spec, ctx)
```

That is the whole extension: the gateway, transport, routing table, daemon and tests need no
change. `register_kind` exists so the extension point is obvious in a diff.

## The one rule every backend obeys

**Routing comes from the origin envelope, never from the agent.** `reply_from_origin()`
copies `channel`, `channel_user_id` and `thread_id` from the inbound message, because only
the gateway saw the human. An agent decides *what* to say; it never decides *where* it goes.
A backend that wants to choose its own routing is a security bug, not a feature.

## Why validation happens at BUILD time

Every spec is validated before any backend is built, and a bad one is a startup error that
names the entry: unknown kind (with the list of known kinds), `kind=command` with no
command, a duplicate name, an unknown key (a typo'd `comand:` must not silently mean "no
command"), a lowercase `subject` (the bus rejects those), a bad `reply_mode`, a missing
`GATEWAY_SECRET` for a hermes backend.

This is not politeness. The cutover rehearsal lost real messages because a placeholder agent
name (`hermes`, from the example config) had **no queue**: dispatch failed, nothing was
logged, and the offset advanced anyway. A gateway that starts up healthy while silently
dropping every message is the failure this validation exists to prevent.

## Verifying a new agent

1. `python3 -m pytest tests/test_gateway_agent_registry.py -q` — the registry, specs, and
   the command backend (including the failure paths).
2. A **live** turn on a second bot token. Fakes accept whatever you hand them, so a kind
   that "passes the unit tests" can still be a wire mismatch — every fault on this path was
   silent until it met the real bus (docs/design/gateway-reply-path.md).
3. `health()` for the new backend via `/status`, which reports the declared spec.
