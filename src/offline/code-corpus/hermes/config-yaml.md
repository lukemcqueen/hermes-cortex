---
language: yaml
tags: [hermes, agent, config, setup]
title: Hermes Agent config.yaml Structure
description: Full reference for config.yaml — profiles, providers, tools, skills, cron, plugins
source: pattern
---

# Hermes Agent `config.yaml` Structure

The main configuration file lives at `~/.hermes/config.yaml` and controls every
aspect of the agent runtime.

## Top-Level Keys

```yaml
# ~/.hermes/config.yaml

profiles: {}              # Named profiles (extends default)
default_profile: default  # Profile to load at startup
providers: {}             # LLM provider configs (OpenAI, Anthropic, etc.)
tools: {}                 # Tool backends (terminal, browser, web, etc.)
skills: {}                # Skill directories and metadata
cron: {}                  # Scheduled tasks
plugins: {}               # Plugin references
memory: {}                # Memory backends
```

## Profiles

Profiles inherit from `default`. Each profile can override providers, tools, and
skills independently.

```yaml
profiles:
  default:
    provider: openai
    model: gpt-4o
    tools:
      terminal: enabled
      web_search: enabled

  code-review:
    extends: default
    model: claude-sonnet-4-20250514
    provider: anthropic
    tools:
      terminal: enabled
      web_search: disabled
      browser: disabled

  research:
    extends: default
    provider: openai
    model: o3-mini
    tools:
      web_search: enabled
      browser: enabled
      terminal: disabled
```

## Providers

Configure LLM providers with API keys, base URLs, and model defaults.

```yaml
providers:
  openai:
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
    default_model: gpt-4o
    max_tokens: 16384
    temperature: 0.7

  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    default_model: claude-sonnet-4-20250514
    max_tokens: 8192

  openrouter:
    api_key: ${OPENROUTER_API_KEY}
    base_url: https://openrouter.ai/api/v1
    default_model: deepseek/deepseek-v3
    fallbacks:
      - anthropic/claude-sonnet-4-20250514
      - openai/gpt-4o

  ollama:
    base_url: http://localhost:11434/v1
    default_model: llama3.2:3b
    api_key: ollama  # placeholder, not validated
```

## Tools

Each tool backend has its own configuration block. Tools can be enabled/disabled
per profile.

```yaml
tools:
  terminal:
    backend: local
    default_timeout: 180
    max_timeout: 600
    allowed_commands:
      - git
      - npm
      - go
      - python3
      - docker
    deny_commands:
      - rm -rf /
      - sudo

  browser:
    backend: browser-use
    headless: true
    viewport:
      width: 1280
      height: 720

  web_search:
    backend: firecrawl
    api_key: ${FIRECRAWL_API_KEY}
    max_results: 5
    crawl_depth: 1

  memory:
    backend: gbrain
    sync_interval: 120
    max_memory_entries: 50

  session_search:
    backend: embedding
    model: text-embedding-3-small
    top_k: 5
```

## Skills

Skills are directories of `.md` files the agent loads at startup. They provide
domain knowledge, tool instructions, and behavioral guidelines.

```yaml
skills:
  paths:
    - ~/.hermes/skills/
    - ~/projects/my-project/.hermes-skills/
  auto_load: true
  watch: false  # re-scan on file changes

  # Inline skill overrides per profile
  overrides:
    code-review:
      exclude:
        - hermes-agent
        - web-development
```

## Cron (Scheduled Tasks)

Define recurring tasks using cron expressions or interval strings.

```yaml
cron:
  memory-sync:
    schedule: "*/2 * * * *"     # every 2 minutes
    profile: default
    task: "Sync brain memory to agent memory"

  daily-summary:
    schedule: "0 8 * * 1-5"     # weekdays at 8 AM
    profile: default
    task: "Generate daily context summary"
    timeout: 120

  health-check:
    schedule: "@every 5m"        # Go-style duration
    profile: default
    task: "Run system health checks"
```

## Plugins

Hermes plugins extend the agent's capabilities. Each plugin is a self-contained
module.

```yaml
plugins:
  paths:
    - ~/.hermes/plugins/
  auto_load: true

  configs:
    brain:
      enabled: true
      slash_command: /brain
      sources:
        - ~/brain/
      sync_daemon: true

    langfuse:
      enabled: true
      public_key: ${LANGFUSE_PUBLIC_KEY}
      secret_key: ${LANGFUSE_SECRET_KEY}
      host: http://localhost:3000
      trace_level: all
```

## Environment Variable Interpolation

Config values support `${VAR_NAME}` and `${VAR_NAME:-default}` syntax. Variables
are resolved from the shell environment at startup.

```yaml
providers:
  custom:
    api_key: ${CUSTOM_API_KEY:?err}        # fail if unset
    base_url: ${CUSTOM_BASE_URL:-https://api.example.com/v1}  # with default
```

## Configuration Validation

Run validation without starting the agent:

```bash
hermes validate config    # validates ~/.hermes/config.yaml
hermes validate config --profile research
```