--- Full content (truncated) ---
---
name: legacy-codebase-navigation
description: "Navigate, understand, and debug large legacy codebases (Rails, Django, early Node). Techniques for tracing data through deep helper chains, reading mutation-heavy code without getting lost, and finding the exact transformation that damaged your data."
version: 1.0.0
author: Hermes Cortex (troubleshooter)
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [legacy, rails, debugging, codebase-navigation, data-tracing]
    related_skills: [root-cause-debugging, project-map, codebase-design]
---

# Legacy Codebase Navigation

## Overview

Legacy codebases share common traits that make them harder to debug than greenfield projects:
- **Deep helper chains** — data passes through 5+ transformation layers (controller → helper → sub-helper → sub-sub-helper)
- **Mutation-heavy code** — `gsub!`, `gsub`, `strip`, `upcase` chained in long sequences, each step mutating state
- **Side-effect rich** — functions set instance variables, write l
... [truncated]
--- End skill ---