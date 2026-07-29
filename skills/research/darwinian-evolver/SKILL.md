--- Full content (truncated) ---
---
name: darwinian-evolver
description: Evolve prompts/regex/SQL/code with Imbue's evolution loop.
version: 0.1.0
author: Bihruze (Asahi0x), Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [evolution, optimization, prompt-engineering, research]
    related_skills: [arxiv]
---

# Darwinian Evolver

Run Imbue's [darwinian_evolver](https://github.com/imbue-ai/darwinian_evolver) — an
LLM-driven evolutionary search loop — to optimize a **prompt, regex, SQL query,
or small code snippet** against a fitness function.

Status: thin wrapper around the upstream tool. The skill installs it, walks the
agent through writing a `Problem` definition (organism + evaluator + mutator),
and drives the loop via the upstream CLI or a small custom Python driver.

**License:** the upstream tool is **AGPL-3.0**. The skill ONLY ever invokes it
via the upstream CLI or a `subprocess`/`uv run` call (mere aggregation). Do NOT
import upstream classes into Hermes
... [truncated]
--- End skill ---