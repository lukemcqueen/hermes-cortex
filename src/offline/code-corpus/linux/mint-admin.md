---
language: shell
tags: [linux, mint, administration, apt, system]
title: Linux Mint Administration
description: Package management, firewall, timeshift, driver manager, and system settings specific to Linux Mint.
source: pattern
---

```bash
# ── Package management (APT) ──
sudo apt update                     # refresh package lists
sudo apt upgrade                    # upgrade all packages
sudo apt full-upgrade               # with dependency resolution
sudo apt install nginx postgresql
sudo apt remove firefox             # remove package
sudo apt autoremove                 # remove orphaned dependencies
apt list --upgradable               # show upgradable packages
apt search "web server"             # search packages
apt show nginx                      # package details

# ── Mint-specific tools ──
mintsources                         # GUI: Software Sources (PPAs, mirrors)
mintdrivers                         # GUI: Driver Manager (NVIDIA, Wi-Fi)
timeshift --create                  # create system snapshot
timeshift --restore                 # restore from snapshot
timeshift --list                    # list snapshots

# ── Firewall (ufw) ──
sudo ufw enable                     # enable firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp               # SSH
sudo ufw allow 80/tcp               # HTTP
sudo ufw allow 443/tcp              # HTTPS
sudo ufw status verbose

# ── System info ──
inxi -F                             # full system info (Mint tool)
inxi -G                             # GPU / display info
lsb_release -a                      # Mint version
hostnamectl                         # system hostname + OS info

# ── Mint Update Manager CLI ──
mintupdate-cli list                 # list available updates
mintupdate-cli upgrade              # install updates
mintupdate-cli refresh              # refresh cache

# ── Flatpak / Snap ──
flatpak list                        # installed flatpaks
flatpak install flathub org.onlyoffice.desktopeditors
flatpak update
```
