--- Full content (truncated) ---
---
name: slime-rl-training
description: Provides guidance for LLM post-training with RL using slime, a Megatron+SGLang framework. Use when training GLM models, implementing custom data generation workflows, or needing tight Megatron-LM integration for RL scaling.
version: 1.0.0
author: Orchestra Research
license: MIT
dependencies: [sglang-router>=0.2.3, ray, torch>=2.0.0, transformers>=4.40.0]
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Reinforcement Learning, Megatron-LM, SGLang, GRPO, Post-Training, GLM]

---

# slime: LLM Post-Training Framework for RL Scaling

slime is an LLM post-training framework from Tsinghua's THUDM team, powering GLM-4.5, GLM-4.6, and GLM-4.7. It connects Megatron-LM for training with SGLang for high-throughput rollout generation.

## When to Use slime

**Choose slime when you need:**
- Megatron-LM native training with SGLang inference
- Custom data generation workflows with flexible data buffers
- Training GLM, Qwen3, DeepSeek V3, or Llama 3 mo
... [truncated]
--- End skill ---