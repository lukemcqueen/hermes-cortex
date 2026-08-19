# State-Transition Watchdog — post only when the state CHANGES

For no_agent crons that remind/alert on a *state* (pending backlog, counter,
dashboards), where every tick produces output even when nothing changed.
Plain silent-when-healthy isn't enough — the condition stays true for hours
and re-delivers the identical message every tick (Telegram spam).

## The Problem (real case 2026-08-20)

`agent-no-verify-audit` (every 10 min) printed the same "SCORING BACKLOG: 2
PENDING cycles" reminder on every tick while the cycles stayed unscored.
Each tick produced non-empty stdout → no_agent cron delivered it verbatim →
identical Telegram messages every 10 minutes. Luke: *"one of the agents had
this multiple times unchanged sent to telegram"*.

## The Pattern

Track a **signature of the reported state** in a JSON state file; print
(and update the signature) only when the current signature differs from the
last-reported one. Identical ticks → empty stdout → silent.

```python
# state.json keys added: last_backlog, last_debt
stale = check_pending_cycles()                       # list[(task_id, ts)]
backlog_sig = sorted(f"{ts}|{task_id}" for task_id, ts in stale)
if backlog_sig and backlog_sig != state.get("last_backlog"):
    print(...)                                       # fire once
    state["last_backlog"] = backlog_sig
elif not backlog_sig and state.get("last_backlog"):
    state["last_backlog"] = []                       # record empty baseline
# ... save_state(state) at end ONLY when changed
```

Rules that make it correct:

1. **Signature = identity of the state, not derived counts.** Use sorted
   per-item ids (`ts|task_id`), not `len(stale)` — count-only dedup misses
   "same count, different cycle".
2. **Record the empty baseline silently.** When the state clears, don't
   post "backlog cleared" — just save `[]` so a later re-accumulation
   compares against empty and re-fires.
3. **Value-based dedup for counters.** For a threshold alert (e.g. debt
   >= 4), fire when the *value changes* (or re-accumulates after a reset):
   `if v >= N and v != state.get("last_v"): ...` and track `last_v = v`
   even when below threshold.
4. **Save state only when changed** (`changed` flag) — avoids pointless
   writes every tick.
5. **First run after deploy posts once.** An old state file lacking the new
   keys yields `None` from `.get()`, which != any signature — one final
   post of the current state, then silence until a real change.

## Verification

RED/GREEN harness: load the script via importlib, override its path
constants to a sandbox dir, drive change/no-change/re-change cycles, assert
stdout. RED against pre-fix code, GREEN 19/19 after. Keep the harness as a
repo test (`tests/test_no_verify_audit_dedup.py`) — the 19 cases cover:
first fire, identical silent, value change, set change, clear, re-accumulation,
event-section regression, fresh env.

## Also

- LLM-driven crons: the same "fire on change" idea via prompt instruction
  (see `silent-when-healthy-pattern.md`) — but for LLM crons the message
  text varies naturally, so dedup is usually about suppressing no-op runs.
- `monitor_script`/`monitor_url` (cronjob MCP) hash script output each tick
  and suppress the agent run entirely when unchanged — the scheduler-level
  equivalent for LLM crons whose *input* state hasn't changed.
