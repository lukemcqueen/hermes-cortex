--- Full content (truncated) ---
---
name: sync-allow-ips-to-fail2ban
version: 1.0.0
description: Sync IPs from allow-ips-manual.conf to fail2ban ignoreip
---

# Sync Allow IPs to fail2ban

## Trigger
User says "add/remove an allow IP" or "sync IPs to fail2ban".

## Workflow — 3 steps (always do ALL):

### Step 1 — Create/update the source script
Script lives at `~/.hermes/scripts/local-sync-allow-ips-to-fail2ban.sh`:

```bash
#!/bin/bash
# Reads IPs from /etc/nginx/allow-ips-manual.conf, strips 127.0.0.1/::1,
# updates ignoreip in /etc/fail2ban/jail.local, reloads fail2ban.

ALLOW_FILE="/etc/nginx/allow-ips-manual.conf"
JAIL_LOCAL="/etc/fail2ban/jail.local"

# Extract IPs/CIDRs (skip comments, strip "allow " and ";")
IPS=$(grep -oP 'allow \K[^;]+' "$ALLOW_FILE" | grep -v '^127\.0\.0\.1$' | grep -v '^::1$' | tr '\n' ' ')

# Build new ignoreip line
NEW_IGNORE="ignoreip = 127.0.0.1/8 ::1 $IPS"

# Replace in jail.local
sed -i "s/^ignoreip = .*/$NEW_IGNORE/" "$JAIL_LOCAL"

# Reload fail2ban
fail2ban-client reload
```

Make it executable
... [truncated]
--- End skill ---