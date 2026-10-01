"""cortex_gateway — the decoupled hermes-cortex gateway package.

Standalone message gateway that owns the full poll → dispatch → reply loop
WITHOUT the Hermes agent runtime. Two seams:

- ``transport`` (CR1): TransportAdapter + TelegramAdapter + bus helpers,
  extracted from ``msg-gateway.py`` (ADR-0005) with identical behavior.
- ``backend`` (CR2): BackendAdapter, the seam an agent backend implements so
  the gateway dispatches an inbound envelope and collects the reply.
  hermes is the first adapter; pi and steadfaste plug into the same seam.

Nothing in this package imports the Hermes agent — it is the migration target
for the in-process ``hermes_cli.main gateway run`` loop.
"""
