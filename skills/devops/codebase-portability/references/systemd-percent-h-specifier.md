# systemd `%h` Home Specifier for Portable Service Files

## Problem

Systemd user service files often contain hardcoded absolute paths like
`~/.hermes/scripts/health-server.py`. These break when:
- The repo is cloned by a different user
- The server is migrated to a machine with a different home directory
- Multiple agents share the same repo but have different HOME directories

## Solution: Use `%h`

Systemd provides **specifiers** — `%`-prefixed tokens resolved at load time:

| Specifier | Resolves to | Example |
|-----------|-------------|---------|
| `%h` | User's home directory | `/home/moses` or `/Users/titus` |
| `%u` | User name | `moses` |
| `%t` | Runtime directory | `/run/user/1000` |
| `%S` | State directory | `~/.local/state` |
| `%E` | Configuration directory | `~/.config` |

**Before (hardcoded):**
```ini
ExecStart=~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/scripts/health-server.py
StandardOutput=append:~/.hermes/health-server/server.log
```

**After (portable):**
```ini
ExecStart=%h/.hermes/hermes-agent/venv/bin/python3 %h/.hermes/scripts/health-server.py
StandardOutput=append:%h/.hermes/health-server/server.log
```

## Limitations

1. **`%h` and `Environment=`** — Environment variables set via `Environment=` are NOT resolved through specifiers. `Environment=PATH=%h/.local/bin` does NOT expand `%h`. You must write the full path in `Environment=` directives.

2. **`%h` in the repo version** — The repo stores the `%h` version so it's portable. When deploying locally, some agents may `sed`-substitute `%h` to the absolute path, or rely on systemd's runtime resolution. Both approaches work — prefer keeping `%h` in the repo file and letting systemd resolve it.

3. **macOS launchd equivalent** — macOS launchd uses `~` or `$HOME` in plist program arguments. However, `launchctl` does NOT resolve `~` in XML plists unless the string is inside `<string>~/path</string>` (tilde expansion by the shell). The more reliable approach is using `$HOME` or `${CORTEX_HOME}` and resolving at install time via `sed`:

   ```xml
   <string>${CORTEX_HOME}/.hermes/scripts/health-server.py</string>
   ```

   With install-time substitution:
   ```bash
   sed "s|\${CORTEX_HOME}|$HOME|g" template.plist > ~/Library/LaunchAgents/com.hermes.service.plist
   ```

## Example: `com.hermes.health-server.service`

From the public Hermes Cortex repo (`ops/scripts/com.hermes.health-server.service`):

```ini
[Unit]
Description=Hermes Cortex Health Server — self-monitoring API
Documentation=https://github.com/fleet-operator/hermes-cortex
After=network.target

[Service]
Type=simple
Environment=PATH=%h/.local/bin:%h/.hermes/hermes-agent/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=%h/.hermes/hermes-agent/venv/bin/python3 %h/.hermes/scripts/health-server.py
Restart=on-failure
RestartSec=5
StandardOutput=append:%h/.hermes/health-server/server.log
StandardError=append:%h/.hermes/health-server/server.log

# Runtime hardening
NoNewPrivileges=yes
ProtectHome=read-only
PrivateTmp=yes
ProtectSystem=strict

[Install]
WantedBy=default.target
```

## Verification

Check that the resolved paths are correct after systemd loads the file:

```bash
systemctl --user show com.hermes.health-server | grep ExecStart
# → ExecStart={ path=~/.hermes/hermes-agent/venv/bin/python3 ; argv[]=~/.hermes/hermes-agent/venv/bin/python3 ~/.hermes/scripts/health-server.py ; ...
```
