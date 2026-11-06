"""cortex_bus — ONE-RELEASE shim for the renamed lib.fleet_bus module (cortex->fleet, 2026-11-06).

The canonical module is now `lib.fleet_bus` (ops/scripts/lib/fleet_bus.py).
This shim makes every legacy `from lib.cortex_bus import bus_send` keep
resolving while peers redeploy. It re-exports the canonical module's public
names — same callables, no copies. DELETE this shim (and its register()
entries) in the release that retires the old name, once
`git grep -l 'lib.cortex_bus'` proves nothing imports it.
"""

from lib.fleet_bus import *  # noqa: F401,F403  (bus_send, bus_read, bus_archive, bus_peek, bus_list_queues, ...)
from lib.fleet_bus import (  # noqa: F401  explicit re-export of the public surface
    CONFIG_FILE,
    BusPermanentError,
    bus_archives,
    bus_archive,
    bus_find_duplicate,
    bus_health,
    bus_list_queues,
    bus_norm_body,
    bus_peek,
    bus_read,
    bus_send,
    learning_capture,
)
