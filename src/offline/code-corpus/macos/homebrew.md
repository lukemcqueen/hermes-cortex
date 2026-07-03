---
language: shell
tags: [macos, homebrew, brew, package-management]
title: macOS Homebrew — Package Management
description: Installing, updating, and managing packages with Homebrew, casks, and taps.
source: pattern
---

```bash
# ── Essentials ──
brew update                       # update formula list
brew upgrade                      # upgrade all installed packages
brew outdated                     # list outdated packages
brew list                         # all installed packages

# ── Search & Install ──
brew search pyenv                 # search for formula
brew install pyenv                # install CLI tool
brew install --cask docker        # install GUI app (cask)
brew tap homebrew/cask-versions   # add alternative versions tap
brew install --cask google-chrome@dev

# ── Services ──
brew services list                # all managed services
brew services start postgresql@16
brew services stop postgresql@16
brew services restart nginx
brew services info ollama          # status + log path

# ── Maintenance ──
brew doctor                       # diagnose common issues
brew cleanup                      # remove old versions
brew cleanup -s                   # + remove cached downloads
brew autoremove                   # remove unused dependencies
brew pin python@3.12              # prevent upgrade
brew unpin python@3.12

# ── Info ──
brew info nginx                   # version, deps, caveats
brew deps --tree nginx            # dependency tree
brew uses --installed nginx       # what depends on nginx
```
