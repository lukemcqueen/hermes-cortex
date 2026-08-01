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

Make it executable:

```bash
chmod +x ~/.hermes/scripts/local-sync-allow-ips-to-fail2ban.sh
```

### Step 2 — Add an allow IP
Append the IP or CIDR to `/etc/nginx/allow-ips-manual.conf` (one per line):

```nginx
allow 203.0.113.45;
allow 198.51.100.0/24;
```

Then run the sync script to propagate to fail2ban:

```bash
bash ~/.hermes/scripts/local-sync-allow-ips-to-fail2ban.sh
```

### Step 3 — Verify
Confirm both layers picked up the IP:

```bash
# nginx layer — should show the allow line
grep -c "allow 203.0.113.45" /etc/nginx/allow-ips-manual.conf

# fail2ban layer — ignoreip should contain it
grep "^ignoreip" /etc/fail2ban/jail.local

# fail2ban reload succeeded
fail2ban-client status | grep -i "number of jail"
```

## Pitfalls

- **Never add `127.0.0.1` or `::1` to the manual file** — they're always in `ignoreip` by construction; adding them is harmless but noisy.
- **The allow file is nginx `allow` directives, not raw IPs** — the extractor strips the `allow ` prefix and trailing `;`. A malformed line (missing `;`) silently drops the IP.
- **`sed` replaces the whole `ignoreip` line** — if jail.local is absent or lacks an `ignoreip` line, the script no-ops; create the line first with `sed -i "s/^ignoreip = .*/ignoreip = 127.0.0.1\/8 ::1/" "$JAIL_LOCAL"`.
- **fail2ban reload is required** — editing jail.local without `fail2ban-client reload` has no effect until the next service restart.
- **Daily threat-pipeline cron** (5AM) deploys blocked IPs from `deploy/nginx/blocked_ips.add` — this allow-list flow is the complementary whitelist; keep them separate.

## Related
- `threat-defense-pipeline` — the blocking side (fail2ban jails + nginx IP blocking)
- `linux-server-hardening` — broader server security posture
