--- Full content (truncated) ---
---
name: blender-mcp
description: Control Blender directly from Hermes via socket connection to the blender-mcp addon. Create 3D objects, materials, animations, and run arbitrary Blender Python (bpy) code. Use when user wants to create or modify anything in Blender.
version: 1.0.0
requires: Blender 4.3+ (desktop instance required, headless not supported)
author: alireza78a
tags: [blender, 3d, animation, modeling, bpy, mcp]
platforms: [linux, macos, windows]
---

# Blender MCP

Control a running Blender instance from Hermes via socket on TCP port 9876.

## Setup (one-time)

### 1. Install the Blender addon

    curl -sL https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py -o ~/Desktop/blender_mcp_addon.py

In Blender:
    Edit > Preferences > Add-ons > Install > select blender_mcp_addon.py
    Enable "Interface: Blender MCP"

### 2. Start the socket server in Blender

Press N in Blender viewport to open sidebar.
Find "BlenderMCP" tab and click "Start Server".

### 3. Ve
... [truncated]
--- End skill ---