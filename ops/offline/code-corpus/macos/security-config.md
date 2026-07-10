---
language: shell
tags: [macos, security, defaults, system]
title: macOS Security & System Configuration
description: Security hardening via defaults, Gatekeeper, FileVault, firewall, and privacy settings.
source: pattern
---

```bash
# ── Gatekeeper ──
spctl --status                     # check Gatekeeper status
spctl --master-disable            # allow apps from anywhere (not recommended)
sudo spctl --master-enable        # re-enable Gatekeeper
xattr -d com.apple.quarantine /path/to/app  # remove quarantine flag

# ── Firewall ──
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --listapps

# ── FileVault (full disk encryption) ──
sudo fdesetup status              # on/off
sudo fdesetup enable              # turn on (requires interactive)
sudo fdesetup list                # list enrolled users

# ── macOS defaults (lockdown) ──
defaults write com.apple.Safari \
  com.apple.Safari.ContentPageGroupIdentifier.WebKit2JavaScriptEnabled -bool false
defaults write /Library/Preferences/com.apple.alf globalstate -int 1  # enable firewall
sudo defaults write /Library/Preferences/com.apple.loginwindow \
  GuestEnabled -bool false         # disable guest account

# ── Keychain ──
security find-internet-password -s github.com  # retrieve stored password
security add-generic-password -a $USER -s myservice -w 'mypass'
security delete-generic-password -s myservice

# ── SSH client (macOS-specific) ──
# ~/.ssh/config — UseKeychain for Touch ID integration
# Host *
#   UseKeychain yes
#   AddKeysToAgent yes
#   IdentityFile ~/.ssh/id_ed25519
```
