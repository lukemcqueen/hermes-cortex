---
language: shell
tags: [macos, launchd, services, system]
title: macOS launchd — Service Management
description: Creating and managing background services with launchd plists, launchctl commands.
source: pattern
---

```bash
# ── launchctl basics ──
launchctl list                         # all running user agents
launchctl list | grep -v com.apple     # third-party services only
launchctl load ~/Library/LaunchAgents/my.plist
launchctl unload ~/Library/LaunchAgents/my.plist
launchctl start my.agent
launchctl stop my.agent
launchctl kickstart -kp gui/501/my.agent  # force restart (kill + start)

# ── User LaunchAgent template (~/Library/LaunchAgents/) ──
# com.example.myagent.plist:
# <?xml version="1.0" encoding="UTF-8"?>
# <plist version="1.0">
# <dict>
#   <key>Label</key>        <string>com.example.myagent</string>
#   <key>ProgramArguments</key>  <array><string>/usr/local/bin/myscript</string></array>
#   <key>RunAtLoad</key>    <true/>
#   <key>KeepAlive</key>    <true/>
#   <key>StandardOutPath</key> <string>/tmp/myagent.log</string>
#   <key>StandardErrorPath</key><string>/tmp/myagent.err</string>
# </dict>
# </plist>

# ── System daemons (/Library/LaunchDaemons/) ──
sudo launchctl load /Library/LaunchDaemons/com.example.daemon.plist

# ── Logs ──
log show --predicate 'process == "myagent"' --last 1h
sudo log show --predicate 'eventMessage contains "com.example"' --last 30m
```
