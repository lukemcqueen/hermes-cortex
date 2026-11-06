# P3 step 3 — rename audit record (2026-11-06)

## Why the review window shows renamed files as "new"

The 35 cortex-* -> fleet-* file renames in this cycle are `git mv`
operations with token-swap content only (verified: `git diff
--find-renames=40% <step-2 base> HEAD` reports each pair as a rename with a
small delta, and `git log --follow -- <new-path>` carries the history). The
governance per-blob review window materialises a rename pair as
delete+add (no rename detection), so a renamed file can read as "new file
mode 100644 / index 00000000..". That is a window limitation, not a content
defect; the true rename record is in the commit metadata.

## Unit/service names deliberately NOT renamed in P3 (P5-deferred)

The following runtime names are load-bearing infrastructure identifiers.
Renaming them now (mid-release) would strand live units, nginx config, and
deployed hosts; the locked rename plan
(docs/plans/cortex-to-fleet-rename-plan.md, `## Rename stages`) defers the
service/unit renames to P5. Confirmed for:

- `cortex-bridge-` unit-family prefix (26 live .service + 53 .timer units)
- `cortex-bus.service` (live active bus unit)
- `cortex-gateway.service` (legacy primary gateway unit, dead/disabled —
  renamed already for the second-bot instance in P2/P3)
- nginx `upstream cortex_bus_backend` block
- docker-compose service names (`cortex-postgres`, etc.)

File and command names for the same components ARE fleet-* (this cycle). The
CORTEX_ env var NAMES are P4-deferred (separate phase).

A prefix difference between a file name (fleet-*) and its generated unit
name (cortex-bridge-*) is therefore intended and time-limited to P5; it is
NOT an incomplete rename.

## Operator direction

- The second-bot gateway unit was renamed cortex-gateway-esther0001.service
  -> fleet-gateway-esther0001.service on Luke's explicit direction
  (2026-11-06), ahead of the P5 service-rename phase — an exception, not the
  rule. The remaining cortex-bus/cortex-bridge unit names stay until P5.