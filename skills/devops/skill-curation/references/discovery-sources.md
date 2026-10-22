# Skill Discovery Sources — Known-Good Registry

## Official (always safe)

| Identifier | Description |
|-----------|-------------|
| `official/productivity/shopify` | Shopify Admin & Storefront GraphQL API via curl |
| `official/mlops/whisper` | OpenAI Whisper local speech recognition |

## skills.sh — Alireza Rezvani (marketing suite, all stdlib Python)

**Source:** `skills-sh/alirezarezvani/claude-skills/<name>`
**Repo:** https://github.com/alirezarezvani/claude-skills

| Skill | Domain | Has Scripts |
|-------|--------|------------|
| content-production | Blog/article writing pipeline | brand_voice_analyzer.py, seo_optimizer.py, content_quality_gates.py, content_scorer.py |
| content-strategy | Topic clusters, calendars, keyword research | topic_cluster_mapper.py |
| copywriting | Homepage/landing/pricing page copy | headline_scorer.py |
| content-humanizer | AI-tell removal, voice injection | humanizer_scorer.py |
| social-content | Multi-platform social media strategy | — |
| social-media-analyzer | Engagement rates, ROI, benchmarks | analyze_performance.py, calculate_metrics.py |
| seo-audit | Full-page SEO audit (scored) | — |
| brand-guidelines | Brand voice/style guide creation | — |
| video-content-strategist | YouTube/TikTok video strategy | — |
| paid-ads | Facebook/Google ad copy & strategy | — |
| email-sequence | Email sequences, newsletters | — |
| campaign-analytics | Multi-channel campaign measurement | — |
| launch-strategy | Product launch planning | — |
| programmatic-seo | Programmatic SEO at scale | — |
| ad-creative | Ad visual copywriting | — |
| x-twitter-growth | X/Twitter growth strategies | — |
| marketing-strategy-pmm | Product marketing strategy | — |
| marketing-psychology | Consumer psychology for messaging | — |
| schema-markup | Schema.org structured data | — |

## skills.sh — Other Collections

| Source | Content |
|--------|---------|
| `skills-sh/winterliu6/hermes-skills/content-studio` | Chinese social media content (小红书/抖音/公众号) |
| `skills-sh/robinberaud/hermes-skills` | Marketing/SEO skills |
| `skills-sh/kostja94/marketing-skills/branding` | Branding and rebranding strategy |
| `skills-sh/auth0/agent-skills/auth0-branding` | Auth0 brand guidelines |

## Sourced But Skipped (violate policy)

| Skill | Reason Skipped |
|-------|---------------|
| social-media-manager | Requires Postiz API (external service) |
| youtube-transcript-api | Requires youtubetranscript.dev API |
| faster-whisper-transcribe | Requires pip install faster-whisper |
| notebooklm-content-creation | Requires notebooklm-mcp-cli external tool |
| social-media-engine | Dangerous scan verdict (curl-pipe-shell, env exfil) |
| content-workflow-engine | Caution verdict (subprocess, exec) |
