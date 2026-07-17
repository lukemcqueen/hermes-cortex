--- Full content (truncated) ---
---
name: pokemon-player
description: "Play Pokemon via headless emulator + RAM reads."
tags: [gaming, pokemon, emulator, pyboy, gameplay, gameboy]
platforms: [linux, macos, windows]
---
# Pokemon Player

Play Pokemon games via headless emulation using the `pokemon-agent` package.

## When to Use
- User says "play pokemon", "start pokemon", "pokemon game"
- User asks about Pokemon Red, Blue, Yellow, FireRed, etc.
- User wants to watch an AI play Pokemon
- User references a ROM file (.gb, .gbc, .gba)

## Startup Procedure

### 1. First-time setup (clone, venv, install)
The repo is NousResearch/pokemon-agent on GitHub. Clone it, then
set up a Python 3.10+ virtual environment. Use uv (preferred for speed)
to create the venv and install the package in editable mode with the
pyboy extra. If uv is not available, fall back to python3 -m venv + pip.

On this machine it is already set up at /home/teknium/pokemon-agent
with a venv ready — just cd there and source .venv/bin/activate.

You also ne
... [truncated]
--- End skill ---