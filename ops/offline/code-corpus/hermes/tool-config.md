---
language: yaml
tags: [hermes, agent, config, setup]
title: Configuring Hermes Tools
description: Configuring terminal, browser, web, memory, and session_search tools
source: pattern
---

# Configuring Hermes Tools

Hermes provides a set of built-in tools that can be configured per profile. Each
tool has a `config` key under the `tools` section of `config.yaml`.

## Terminal Tool

Controls shell execution. Supports local and SSH backends.

```yaml
tools:
  terminal:
    enabled: true
    backend: local          # local | ssh
    default_timeout: 180
    max_timeout: 600
    workdir: /home/user/projects
    pty: false              # pseudo-terminal for interactive commands

    # Local backend
    local:
      shell: /bin/zsh
      env:
        PATH: /usr/local/bin:/usr/bin:/bin
        GOFLAGS: -mod=mod

    # SSH backend
    ssh:
      host: myserver.example.com
      user: deploy
      port: 22
      identity_file: ~/.ssh/deploy_key
      jump_host: bastion.example.com
      env:
        DEBIAN_FRONTEND: noninteractive

    # Security constraints
    allowlist:
      - git
      - go
      - npm
      - docker
      - python3
    denylist:
      - "rm -rf /"
      - "> /dev/sda"
      - "dd if="
      - "mkfs."
      - ":(){ :|:& };:"  # fork bomb
```

### Per-Profile Overrides

```yaml
profiles:
  prod-deploy:
    extends: default
    tools:
      terminal:
        denylist:
          - rm
          - mv
          - docker system prune
        workdir: /srv/app
        timeout: 60
```

## Browser Tool

Controls browser automation (Browser Use / Playwright). Used for web UI
navigation and scraping.

```yaml
tools:
  browser:
    enabled: false           # disabled by default
    backend: browser-use    # browser-use | playwright
    headless: true
    viewport:
      width: 1280
      height: 720
    locale: en-US
    timezone: America/New_York
    user_agent: >-
      Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)
      AppleWebKit/537.36 (KHTML, like Gecko)
      Chrome/125.0.0.0 Safari/537.36

    # Navigation limits
    max_steps: 50
    wait_between_actions: 500  # ms
    screenshot_on_error: true
    record_video: false

    # Anti-detection
    stealth: true
    disable_web_security: false

    # Cookie persistence
    session_persistence: true
    session_dir: ~/.hermes/browser-sessions/
```

### Dynamic Context

Pass extra context for specific browsing sessions:

```yaml
tools:
  browser:
    extra_context:
      authenticated_domains:
        - github.com
        - linear.app
        - notion.so
      allowed_downloads:
        - ".pdf"
        - ".csv"
```

## Web (Search & Crawl) Tool

Handles web search, content fetching, and crawling.

```yaml
tools:
  web_search:
    enabled: false
    backend: firecrawl      # firecrawl | tavily | serpapi
    api_key: ${FIRECRAWL_API_KEY}
    max_results: 5
    crawl_depth: 1
    crawl_max_pages: 10

    # Content filtering
    allowed_domains:
      - github.com
      - go.dev
      - pkg.go.dev
    blocked_domains:
      - youtube.com
      - reddit.com

    # Rate limiting
    rate_limit:
      requests_per_minute: 30
      concurrent_requests: 3

    # Caching
    cache:
      enabled: true
      ttl: 3600              # seconds
      backend: sqlite
      path: ~/.hermes/cache/web.db

    # Fallback backends
    fallbacks:
      - backend: httpx       # direct HTTP fetch
        timeout: 10
        user_agent: HermesAgent/1.0
```

## Memory Tool

Controls agent memory — knowledge retention, brain sync, and vector search.

```yaml
tools:
  memory:
    enabled: true
    backend: gbrain          # gbrain | memdir | sqlite | chroma

    # gbrain (recommended — Postgres + pgvector via Docker, or PGLite for dev)
    gbrain:
      brain_dir: ~/brain/
      sources:
        - ~/brain/personal/
        - ~/brain/projects/
        - ~/brain/learnings/
      sync_interval: 120     # seconds
      sync_daemon: true
      embedding_model: nomic-embed-text-v1.5
      max_chunk_size: 512
      chunk_overlap: 64
      similarity_threshold: 0.75

    # memdir (flat-file memory)
    memdir:
      path: ~/.hermes/memory/
      max_entries: 50
      max_age_days: 90
      format: markdown

    # Memory scoring
    scoring:
      enabled: true
      min_score: 7           # out of 12
      dimensions:
        relevance: 4
        accuracy: 4
        conciseness: 2
        durability: 2

    # Automatic operations
    auto_sync: true
    auto_prune: true
    prune_threshold: 100     # entries
```

## Session Search Tool

Provides semantic search across the current session history.

```yaml
tools:
  session_search:
    enabled: true
    backend: embedding       # embedding | keyword | hybrid

    embedding:
      model: text-embedding-3-small
      dimensions: 1536
      top_k: 5
      similarity_threshold: 0.7
      batch_size: 10

    # Keyword fallback
    keyword:
      top_k: 10
      case_sensitive: false
      stemming: true

    # Hybrid search configuration
    hybrid:
      embedding_weight: 0.7
      keyword_weight: 0.3

    # Caching
    cache:
      enabled: true
      ttl: 300                # seconds
      max_entries: 100

    # Context window
    max_context_tokens: 4096
    include_timestamps: true
    include_tool_calls: true
```

## Tool Groups

Enabling/disabling tools in bulk for specific profiles:

```yaml
# ~/.hermes/config.yaml

tool_groups:
  coding:
    tools:
      - terminal
      - session_search
      - memory

  research:
    tools:
      - web_search
      - browser
      - memory
      - session_search

  readonly:
    tools:
      - session_search
      - memory

profiles:
  writer:
    extends: default
    tool_group: readonly
  full-access:
    extends: default
    tool_group: coding
    extra_tools:
      - browser
```

## Verification

Check which tools are active for your current profile:

```bash
hermes status                    # shows active tools
hermes status --profile research # specific profile
hermes tool list                 # list all available tools
hermes tool test terminal        # test a specific tool
```

## Tool-Specific Skill Files

Place tool configuration guidance in skill files so the agent can reference it:

```
~/.hermes/skills/hermes-agent/
├── SKILL.md
├── terminal-tool.md
├── browser-tool.md
├── web-tool.md
├── memory-tool.md
└── session-search-tool.md
```