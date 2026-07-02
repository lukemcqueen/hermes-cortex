### Deployment (each server agent)


1. Open the firewall port:
   ```bash
   sudo ufw allow <PORT>/tcp
   ```
2. Run health-vector server (port varies per agent):
   ```bash
   python3 ~/hermes-cortex/src/scripts/health-vector.py --ser

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-02T07:11:47.551874+00:00


---

### Deployment (Titus / macOS client-only)


Titus cannot be polled (no inbound). Instead he pushes to Moses' inbox:

1. **Pull hermes-cortex** and set up `~/.hermes/moses-inbox.conf` with his own credentials:
   ```ini
   MOSES_INBOX_URL="http

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-02T07:11:47.552371+00:00
