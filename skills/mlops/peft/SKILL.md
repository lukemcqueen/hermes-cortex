--- Full content (truncated) ---
---
name: peft-fine-tuning
description: Parameter-efficient fine-tuning for LLMs using LoRA, QLoRA, and 25+ methods. Use when fine-tuning large models (7B-70B) with limited GPU memory, when you need to train <1% of parameters with minimal accuracy loss, or for multi-adapter serving. HuggingFace's official library integrated with transformers ecosystem.
version: 1.0.0
author: Orchestra Research
license: MIT
dependencies: [peft>=0.13.0, transformers>=4.45.0, torch>=2.0.0, bitsandbytes>=0.43.0]
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Fine-Tuning, PEFT, LoRA, QLoRA, Parameter-Efficient, Adapters, Low-Rank, Memory Optimization, Multi-Adapter]

---

# PEFT (Parameter-Efficient Fine-Tuning)

Fine-tune LLMs by training <1% of parameters using LoRA, QLoRA, and 25+ adapter methods.

## When to use PEFT

**Use PEFT/LoRA when:**
- Fine-tuning 7B-70B models on consumer GPUs (RTX 4090, A100)
- Need to train <1% parameters (6MB adapters vs 14GB full model)
- Want fast iterat
... [truncated]
--- End skill ---