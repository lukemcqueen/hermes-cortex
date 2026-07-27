---
name: fresh-tomato-router
description: Interact with FreshTomato/DD-WRT routers programmatically via curl — authentication, nvram access, port forwarding, DMZ, and configuration management.
version: 1.0.0
author: Moses
trigger: when you need to check or modify router settings on a FreshTomato or DD-WRT based router
platforms: [linux]
---

# FreshTomato Router Administration

Procedures for programmatic interaction with FreshTomato-based routers (descended from Tomato/DD-WRT firmware) using curl and shell commands.

## Authentication

### Username: root (not admin)
FreshTomato uses `root` as its admin username. Attempting `admin` will produce a persistent `401 Unauthorized` response even with the correct password. This is a common 15-minute time sink.

```bash
# ✅ Works (root as username)
curl -sk --basic -u "root:$(cat ~/.asus)" https://192.168.1.1:8443/

# ❌ Fails (admin as username — even with correct password)
curl -sk --basic -u "admin:$(cat ~/.asus)" https://192.168.1.1:8443/
# → 401 Unauthorized
```

### Scheme: HTTP Basic Auth per request
FreshTomato uses HTTP Basic Authentication (`WWW-Authenticate: Basic realm="FreshTomato"`) on every request, not a session cookie or form-based login. Pass `--basic -u "user:pass"` on every curl invocation.

⚠️ **Password safety:** Never write the password literal into a command. Use `$(cat /path/to/password)` or a clean temp file (see `secure-credential-handling` skill).

### Port
FreshTomato often runs HTTPS on a non-standard port. Common: `:8443`.

## Page Navigation

### How pages work
FreshTomato loads page content via AJAX from a single-page app. ASP pages contain inline nvram JavaScript objects with the configuration data. The URL format follows a pattern from the navigation tree:

```
/{category}-{page}.asp
```

### Key pages
| Page | URL | Purpose |
|------|-----|---------|
| Status | `/` or `/about.asp` | Overview, connectivity |
| Forwarding Basic | `/forward-basic.asp` | **Port forwarding rules** |
| Forwarding IPv6 | `/forward-basic-ipv6.asp` | IPv6 forwarding |
| DMZ | `/forward-dmz.asp` | DMZ host settings |
| Triggered | `/forward-triggered.asp` | Port triggering |
| UPnP | `/forward-upnp.asp` | UPnP configuration |
| DHCP | `/basic-network.asp` | Network config, DHCP |
| DHCP Res | `/forward-static.asp` | Static DHCP reservations |
| Shell | `/shell.cgi` | Command execution (see below) |

### Note on direct page access
Some bare `.asp` pages (e.g., `/forward.asp`) return `500 Read error`. Always use the full navigation path format with the category prefix.

## Port Forwarding

Port forwarding configuration is stored in `nvram.portforward` as a single pipe-delimited string embedded inline in `/forward-basic.asp`:

```html
nvram = {
    'portforward': '1<1<<14001<<192.168.1.36<Esther App 1>...'
}
```

### Data format
Each rule is delimited by `>` between entries, fields separated by `<`:

```
enabled<protocol<ext_port<local_port<local_ip<description
```

| Field | Position | Values | Notes |
|-------|----------|--------|-------|
| enabled | 0 | `1`=ON, `0`=OFF | |
| protocol | 1 | `1`=TCP, `2`=UDP, `3`=Both | |
| ext_port | 2 | integer or range (e.g., `20:21`) | Empty = same as int_port |
| local_port | 3 | integer or range | Empty = same as ext_port |
| local_ip | 4 | IPv4 address | Target LAN IP |
| description | 5 | string | Human-readable name |

### How to read

```bash
# Extract the nvram.portforward value
curl -sk --basic -u "root:$(cat ~/.asus)" \
  "https://192.168.1.1:8443/forward-basic.asp" | \
  grep -oP "portforward':\s*'[^']+"
```

### How to update
The page has a form that submits to `tomato.cgi` with a `portforward` hidden input. The form data includes `_nextpage=forward-basic.asp` for the redirect-back target.

## DMZ

DMZ settings live in `/forward-dmz.asp`:

```
nvram.dmz_enable — '1' or '0'
nvram.dmz_ipaddr — DMZ target IP
nvram.dmz_sip    — Source IP filter (optional)
```

## Shell Command Execution

FreshTomato has a `shell.cgi` endpoint that can execute arbitrary shell commands on the router:

```bash
curl -sk --basic -u "root:$(cat ~/.asus)" \
  -X POST "https://192.168.1.1:8443/shell.cgi" \
  -d "action=execute&command=nvram+show+|+grep+forward"
```

This runs commands as root on the router. Useful for dumping nvram, checking iptables rules, or restarting services without the web UI.

## Navigation Structure

The side navigation is built dynamically in JavaScript. The nav tree can be found in `tomato.js`. Key sections:

- **Status:** overview, device list, logs
- **Basic:** network, IPv6, identification, time, DDNS, DHCP reservation
- **Advanced:** firewall, adblock, routing, VLAN, wireless
- **Port Forwarding:** basic, basic IPv6, DMZ, triggered, UPnP
- **Administration:** access, config, scripts, upgrade

## Password File Location

The router password file is at `~/.asus` (not `~/.asus_password`). This is a single-line file containing the FreshTomato admin password.

```bash
cat ~/.asus
# → outputs: <password>
```

Always reference it via subshell: `$(cat ~/.asus)`. Never embed the literal password into commands or scripts.

## End-to-End Port Verification Chain

When a port is unreachable despite a router forwarding rule being configured and enabled, the issue can be in any of four layers. Check them in order:

### Layer 1: Router Port Forward
1. Read the forward rule from the router: `curl -sk --basic -u "$(cat ~/.asus)" "…/forward-basic.asp" | grep -oP "portforward':\\s*'[^']+"`
2. Verify: rule exists, **enabled** (first field is `1`), target IP is correct, target port is correct

### Layer 2: nginx Proxy (if the port forwards to a nginx server)
1. Verify nginx is running on the target machine: `systemctl is-active nginx` or `pgrep nginx`
2. Check that nginx is listening on the target port: `ss -tlnp | grep <port>`
3. If nginx is NOT listening on the port, the nginx site config needs a `listen <port> ssl;` directive

### Layer 3: UFW / Firewall on Target Machine
1. Check if UFW is active: `sudo ufw status`
2. Check if the port is allowed: `sudo ufw status | grep <port>`
3. If the port is missing, allow it: `sudo ufw allow <port>`
4. Test TCP reachability from a different LAN machine (e.g., Moses):
   ```bash
   timeout 5 bash -c 'echo > /dev/tcp/<target-ip>/<port> 2>&1 && echo "OPEN" || echo "CLOSED"'
   ```
   - **OPEN** = port accepts connections (fast response)
   - **CLOSED** = port sends RST (immediate "Connection refused")
   - **Hang + timeout** = firewall silently drops packets (like UFW deny or iptables DROP)

### Layer 4: Service Not Running
1. Check the listening service: `ss -tlnp | grep <port>` — if nothing shows, the service isn't listening
2. Check the service health: `systemctl --user status <service>` or `curl http://127.0.0.1:<internal-port>/health`
3. Check UFW is allowing the service's internal port (not just the nginx external port)

### Common Patterns

| Symptom | Likely Layer | Test |
|---------|-------------|------|
| External HTTP 000 (timeout), internal LAN also timeout | Layer 3 (UFW drop) or Layer 1 (router not forwarding) | Check UFW first; then check router rule |
| External HTTP 000, internal LAN immediate "connection refused" | Layer 4 (service down) | `ss -tlnp` on target machine |
| External HTTP 000, internal LAN has `HTTP 200` | Layer 1 (router forward not set) | Check router nvram |
| External HTTP 401, internal LAN has `HTTP 200` | Layer 2 (nginx auth) works | Correct — nginx is present, just needs auth |
| External HTTP 000 on one port, HTTP 200 on another (e.g., :14007 works but :14004 doesn't) | Layer 3 (UFW blocking specific port on target) | `sudo ufw status \| grep <port>` on target machine |

## Verification

After changing port forwarding rules, verify end-to-end:

```bash
# Check from outside the LAN (replace with your public IP)
curl -s -o /dev/null -w "%{http_code}" http://your.public.ip:80

# Check locally on the target server
ss -tlnp | grep -E ':(80|443) '
```
