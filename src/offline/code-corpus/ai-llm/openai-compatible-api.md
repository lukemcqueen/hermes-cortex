---
language: python
tags: [ai, llm, openai, api, streaming, function-calling]
title: OpenAI-Compatible API Patterns
description: Chat completions, streaming, and function/tool calling using the OpenAI Python SDK with any OpenAI-compatible endpoint (OpenAI, Ollama, LiteLLM, etc.)
source: pattern
---

```python
from openai import OpenAI
import json

# ——— Configure for any OpenAI-compatible endpoint ———
# OpenAI native:
#   client = OpenAI(api_key="sk-...")
#
# Ollama (local):
#   client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
#
# LiteLLM proxy:
#   client = OpenAI(base_url="http://localhost:8000/v1", api_key="sk-...")

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",  # Ollama accepts any string
)

# ——— Basic chat completion ———
def chat_completion(model: str = "gpt-4o-mini", messages: list = None):
    resp = client.chat.completions.create(
        model=model,
        messages=messages or [{"role": "user", "content": "Hello!"}],
    )
    return resp.choices[0].message.content

# ——— Streaming ———
def stream_completion(model: str = "gpt-4o-mini", messages: list = None):
    stream = client.chat.completions.create(
        model=model,
        messages=messages or [{"role": "user", "content": "Tell me a story."}],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            print(delta.content, end="", flush=True)
    print()

# ——— Function / Tool calling ———
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, e.g. 'Tokyo'",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "default": "celsius",
                    },
                },
                "required": ["location"],
            },
        },
    }
]

def call_with_tools(model: str = "gpt-4o-mini"):
    """Send a query that triggers a tool call."""
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
        tools=tools,
        tool_choice="auto",
    )
    msg = resp.choices[0].message
    if msg.tool_calls:
        for tc in msg.tool_calls:
            print(f"  Tool called: {tc.function.name}")
            print(f"  Arguments:    {tc.function.arguments}")
            # Simulate execution
            result = json.dumps({"temperature": 22, "unit": "celsius"})
            # Send result back to model
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "What's the weather in Tokyo?"},
                    msg,
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    },
                ],
                tools=tools,
            )
            return response.choices[0].message.content
    return msg.content

# ——— JSON mode ———
def structured_output(model: str = "gpt-4o-mini"):
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "List 3 colors as JSON array."}],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)

if __name__ == "__main__":
    print("Basic:", chat_completion())
    print("Tool call:", call_with_tools())
    print("Structured:", structured_output())
```