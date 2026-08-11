---
language: python
tags: [ai, llm, ollama, local, inference]
title: Ollama API — Chat & Embeddings
description: Calling Ollama's local API for chat completion, generation, and embeddings.
source: pattern
---

```python
import json, urllib.request

OLLAMA = "http://localhost:11434"

# ── Chat completion ──
def chat(model: str, prompt: str, system: str = "") -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7}
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["message"]["content"]

# Usage: chat("qwen2.5:3b", "Write a binary search in Rust")

# ── Text generation (non-chat) ──
def generate(model: str, prompt: str) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048}
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())["response"]

# ── Embeddings ──
def embed(text: str, model: str = "nomic-embed-text") -> list[float]:
    payload = json.dumps({"model": model, "input": text}).encode()
    req = urllib.request.Request(
        f"{OLLAMA}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["embeddings"][0]

# Usage: vec = embed("How do I set up nginx?")  # returns 768 floats
```
