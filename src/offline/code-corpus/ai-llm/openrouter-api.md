---
language: python
tags: [ai, llm, openrouter, api, multi-model, routing]
title: OpenRouter API — Multi-Model Router
description: Using OpenRouter to access 200+ models with fallbacks, model routing, and cost tracking.
source: pattern
---

```python
import openai, os

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    # Identify your app (optional, for rankings)
    default_headers={
        "HTTP-Referer": "https://github.com/your-project",
        "X-Title": "Hermes Cortex",
    }
)

# ── Basic chat ──
response = client.chat.completions.create(
    model="openai/gpt-4o-mini",  # or any provider/model
    messages=[{"role": "user", "content": "Hello!"}]
)

# ── Model routing (auto-pick best available) ──
response = client.chat.completions.create(
    model="openai/gpt-4o-mini",   # preferred
    messages=[{"role": "user", "content": "Write code"}],
    # Fallbacks if preferred is down:
    extra_body={
        "provider": {
            "order": ["OpenAI", "Azure", "Together"],
            "allow_fallbacks": True,
        }
    }
)

# ── Multiple models in one request (cascade) ──
# OpenRouter routes to the cheapest model that can handle it
response = client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
    extra_body={"models": ["openai/gpt-4o-mini", "anthropic/claude-3-haiku", "google/gemini-1.5-flash"]}
)

# ── Cost & usage ──
# Check response.usage for token counts
# OpenRouter charges per-token, supports prepaid credits
# Model pricing: https://openrouter.ai/models

# ── Common model slugs ──
# openai/gpt-4o-mini              — cheap, fast (default workhorse)
# openai/gpt-4o                   — best quality
# anthropic/claude-sonnet-4       — coding specialist
# anthropic/claude-3.5-sonnet     — previous gen
# google/gemini-2.0-flash-001     — Google's fast model
# meta-llama/llama-3.3-70b-instruct  — open-weight
# nousresearch/hermes-3-llama-3.1-405b  — Nous flagship
# deepseek/deepseek-v4-flash      — current deepseek
# mistralai/mistral-large-2411    — Mistral's best
```
