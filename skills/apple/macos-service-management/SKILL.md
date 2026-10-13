---
name: macos-service-management
version: 1.0.0
description: Manage and troubleshoot macOS launchd services — plist authoring, exit code diagnosis, variable expansion rules, and service lifecycle
category: apple
---

# macOS Service Management (launchd)

Manage and debug launchd-based daemons and user agents on macOS. Launchd is macOS's system-wide service manager — analogous to systemd on Linux but with very different rules for paths, variables, and service configuration.

## Key Differences from systemd

| Concept | systemd (Linux) | launchd (macOS) |
|---------|----------------|-----------------|
| Unit file | `.service` | `.plist` (XML property list) |
| User services | `~/.config/systemd/user/` | `~/Library/LaunchAgents/` |
| System services | `/etc/systemd/system/` | `/Library/LaunchDaemons/` |
| User home variable | `%h` (expanded) | `$HOME` — **only in specific fields** |
| Shell variable expansion | Full (all env vars) | **None** — only `$HOME`, `$USER`, tilde `~` |
| Exit code 78 | N/A | EX_CONFIG — config error, launchd refuses to load |
| Reload | `systemctl daemon-reload` | `launchctl unload` + `load` (or `bootout`/`bootstrap`) |

## Service Lifecycle

```bash
# Load / start
launchctl load ~/Library/LaunchAgents/com.example.service.plist
# Modern form:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.service.plist

# Stop / unload
launchctl unload ~/Library/LaunchAgents/com.example.service.plist
# or
launchctl bootout gui/$(id -u)/com.example.service

# Check status
launchctl list | grep example
# OR status with exit code: launchctl print gui/$(id -u)/com.example.service
```

## Plist Authoring

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.example.service</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/my-service</string>
        <string>--flag</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>WorkingDirectory</key><string>/Users/luke/project</string>
    <key>StandardOutPath</key><string>/tmp/my-service.log</string>
    <key>StandardErrorPath</key><string>/tmp/my-service.err</string>
</dict>
</plist>
```

Validate: `plutil -lint com.example.service.plist`

## Variable Expansion Rules

- `$HOME` and `$USER` **are** expanded — but only in select keys
  (ProgramArguments, WorkingDirectory, paths).
- `~` tilde **is** expanded at the start of a path.
- **No other shell variables or `$(...)` are expanded.** A plist is NOT a shell script — write the full path.
- Environment variables for the child process go in an explicit
  `<key>EnvironmentVariables</key>` dict.

## Exit Code Diagnosis

| Exit code | Meaning | Action |
|-----------|---------|--------|
| 0 | Clean exit | Normal (if KeepAlive, it restarts) |
| 1 | Generic error | Check the program's own logs |
| 78 | EX_CONFIG — bad plist | `plutil -lint` the plist; fix syntax |
| 126/127 | Command not found / not executable | Fix ProgramArguments path or `chmod +x` |

A service that exits immediately with 78 means **launchd rejected the plist
config itself** — the process never ran. Fix the plist, not the program.

## Restart-on-exit: the exit code must match the KeepAlive condition

launchd defines exactly five KeepAlive conditions — `SuccessfulExit`,
`NetworkState`, `PathState`, `OtherJobEnabled`, `Crashed`. Read them from the man
page (`man 5 launchd.plist`); **anything else in a KeepAlive dict is not a
condition**, so launchd finds no reason to restart the job and falls back to
demand-only launching.

| KeepAlive condition | Relaunches after | A deliberate self-restart must exit |
|---|---|---|
| `<true/>` | any exit | `0` |
| `SuccessfulExit` **true** | exit status 0 only | `0` |
| `SuccessfulExit` **false** | the INVERSE: exit status **non-zero** | non-zero (`75`, EX_TEMPFAIL) |
| `Crashed` true | a signal-terminated death only | n/a — a clean exit is not restarted |

- **`SuccessfulExit=false` does NOT mean "restart after a clean exit".** Apple's
  wording is "restarted in the inverse condition": the job comes back on a NON-zero
  status and a clean `exit 0` **PARKS** it. A restart command written for systemd
  (`os._exit(0)` under `Restart=always`) therefore stops the service silently — the
  exact failure the policy was added to fix. `systemctl`-shaped restart logic ported
  to launchd without changing the exit code is the trap.
- **`CrashedOrAbnormalExit` is not a launchd key.** It appears in no man page, so a
  KeepAlive dict carrying only it gives launchd no reason to restart: the job stays
  down after any exit. Replace it with `SuccessfulExit=false` + a non-zero exit code,
  or `<true/>` + exit 0.
- **Derive the exit code from the supervisor; never assume 0.** One binary may run
  under systemd (`Restart=always` → 0) or launchd (`SuccessfulExit=false` → 75).
  Prove which job owns the process with `launchctl list`: its **PID column** showing
  OUR pid is the test, because `XPC_SERVICE_NAME` is inherited by every child exactly
  as systemd's `INVOCATION_ID` is. Then read the job's OWN plist (`plutil -p` or
  `plistlib`) and exit with the code that policy relaunches on; when no recognised
  condition covers a deliberate exit, refuse and name the plist fix rather than
  exiting into silence.
- **Confirm a relaunch with the job, not the chat:** `launchctl list <label>` shows a
  NEW pid, and `LastExitStatus` is recorded as `exit_code << 8` (75 → 19200).

## Pitfalls

- ❌ **KeepAlive with unknown keys** — a dict of keys launchd does not define (e.g.
  `CrashedOrAbnormalExit`) is the same as no KeepAlive at all: no restart, and the
  supervisor looks configured. `plutil -lint` passes; only the man page can tell you.
- ❌ **Shell variables in ProgramArguments** — `$(which python3)` does NOT
  expand. Use the absolute path.
- ❌ **Unloaded vs stopped** — `launchctl unload` removes the service
  definition; a stopped-but-loaded service stays defined and can be restarted.
- ❌ **Per-user vs system** — a plist in `~/Library/LaunchAgents` runs as you;
  `/Library/LaunchDaemons` runs as root. Don't put a user's credentials in a daemon.
- ❌ **KeepAlive=true with a crash-looping process** — launchd will restart it
  forever, hammering the CPU. Add a `ThrottleInterval` (default 10s) or fix the crash.

## Related
- `macos-computer-use` — macOS desktop automation
- `server-administration` — the Linux-side equivalent (systemd)
