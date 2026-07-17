--- Full content (truncated) ---
---
name: openhands
description: Delegate coding to OpenHands CLI (model-agnostic, LiteLLM).
version: 0.1.0
author: Tim Koepsel (xzessmedia), Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Coding-Agent, OpenHands, Model-Agnostic, LiteLLM]
    related_skills: [claude-code, codex, opencode, hermes-agent]
---

# OpenHands CLI

Delegate coding tasks to the [OpenHands CLI](https://github.com/All-Hands-AI/OpenHands) via the `terminal` tool. OpenHands is model-agnostic: any LiteLLM-supported provider (OpenAI, Anthropic, OpenRouter, DeepSeek, Ollama, vLLM, etc.).

This skill is the headless-mode wrapper for batch / one-shot delegation. The interactive textual UI is not used from Hermes.

## When to Use

- User wants a coding task delegated to OpenHands specifically.
- User wants a coding agent that can run on a non-Anthropic / non-OpenAI provider (DeepSeek, Qwen, Ollama, vLLM, Nous, etc.) — sibling skills `claude-code` and `codex` are tied to one vendor.
- M
... [truncated]
--- End skill ---