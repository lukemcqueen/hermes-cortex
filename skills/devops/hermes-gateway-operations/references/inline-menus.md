# Inline menus (buttons) for a gateway command

How a slash command returns a tappable picker instead of a free-text argument. Read the live
code before trusting any name below — these are the cortex gateway's, and the authoritative
config key names live in its own example file, not here.

## Where it lives

| Piece | Path |
|---|---|
| Command dispatch + menu state | `ops/scripts/cortex_gateway/daemon.py` |
| Transport (send / edit / buttons / callbacks) | `ops/scripts/cortex_gateway/transport.py` |
| Config, incl. the curated list | `ops/scripts/gateway.yaml`; shape documented in `ops/scripts/gateway.yaml.example` |
| Parity tests | `tests/test_gateway_slash_parity.py` |
| Committed re-runnable proof | `docs/evidence/verify-model-picker.sh` |

## The plumbing to look for first

Check for each of these before writing any of them:

- a button-markup builder for the platform (inline keyboard rows);
- `send(..., buttons=...)`;
- edit-in-place (`editMessageText`) so a press rewrites the message instead of posting a new one;
- callback delivery as a DISTINCT kind on the poll loop, with the callback data in the body — in
  this gateway a press arrives as `tg_kind="callback"` with a body like `[callback: <data>]`,
  so it can be routed before it is mistaken for a user prompt.

Feature-detect each: on a platform without them the command must still work in its
argument form.

## Callback data: indices, not values

`callback_data` is capped (Telegram: 64 bytes) and real values are long (a model id runs 40+).
Encode the page and the slot index, then re-resolve the value from CURRENT state when the press
arrives. What that buys, and what to assert:

- a re-render never needs the old payload — the list may have changed under the button;
- a stale press can only be OUT OF RANGE, which is answered ("that entry is no longer in the
  list") and never applied;
- an unknown or foreign callback clears the spinner and does nothing else.

## Menu semantics that matter

- Tick the value IN FORCE (the backend's own default until the chat overrides it); a menu that
  ticks only overrides shows nothing in the common case.
- Offer a reset entry only when an override exists.
- `page_size` comes from config; pagination moves within the curated list.
- Warn on stderr for unusable entries — `N blank entries ignored (M usable)` — rather than
  serving a silently shorter menu.
- The curated list is the operator's: the backend's full catalogue is hundreds of entries, and a
  menu of hundreds is worse than a command.

## Test cases (parity file, stub transport + echoing backend)

1. the first page renders the configured page size and ticks the default;
2. paging forward/back moves the window and the page marker;
3. a press switches the chat's value and the tick follows;
4. an out-of-range or foreign callback is answered without changing anything;
5. with NO list configured the command falls back to the text form, and the explicit
   `<command> <value>` form still works;
6. deployed copy == repo modulo the deploy banner (the picker's symbols present in both).

A stub transport is what makes these hermetic: a probe that polls with the real bot token
starts a second poller and steals the live channel's messages (409).
