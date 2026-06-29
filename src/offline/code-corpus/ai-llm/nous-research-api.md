---
language: python
tags: [ai, llm, nous-research, hermes, api, openai-compatible]
title: Nous Research API — Hermes Models
description: Using Nous Research's OpenAI-compatible API for Hermes model inference, chat, and function calling.
source: pattern
---

```python
import openai, os

# ── Configuration ──
client = openai.OpenAI(
    base_url="https://api.nousresearch.com/v1",
    api_key=os.environ["NOUS_API_KEY"],  # get from https://nousresearch.com
)

# ── Chat completion ──
response = client.chat.completions.create(
    model="hermes-3-llama-3.1-405b",  # or hermes-3-llama-3.1-70b, hermes-2-pro-mistral-7b
    messages=[
        {"role": "system", "content": "You are a helpful coding assistant."},
        {"role": "user", "content": "Write a Python function to merge two sorted lists."}
    ],
    temperature=0.7,
    max_tokens=1024,
)
print(response.choices[0].message.content)

# ── Streaming ──
stream = client.chat.completions.create(
    model="hermes-3-llama-3.1-405b",
    messages=[{"role": "user", "content": "Explain Rust ownership in 3 sentences."}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")

# ── Function calling ──
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "units": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            },
            "required": ["location"]
        }
    }
}]

response = client.chat.completions.create(
    model="hermes-3-llama-3.1-405b",
    messages=[{"role": "user", "content": "What's the weather in Seoul?"}],
    tools=tools,
    tool_choice="auto",
)

# ── Available models ──
# hermes-3-llama-3.1-405b    — flagship 405B, best quality
# hermes-3-llama-3.1-70b     — fast, good quality
# hermes-2-pro-mistral-7b    — lightweight, open-weight
# hermes-2-pro-llama-3-8b    — balanced speed/quality
```
