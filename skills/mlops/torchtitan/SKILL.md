--- Full content (truncated) ---
---
name: distributed-llm-pretraining-torchtitan
description: Provides PyTorch-native distributed LLM pretraining using torchtitan with 4D parallelism (FSDP2, TP, PP, CP). Use when pretraining Llama 3.1, DeepSeek V3, or custom models at scale from 8 to 512+ GPUs with Float8, torch.compile, and distributed checkpointing.
version: 1.0.0
author: Orchestra Research
license: MIT
dependencies: [torch>=2.6.0, torchtitan>=0.2.0, torchao>=0.5.0]
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Model Architecture, Distributed Training, TorchTitan, FSDP2, Tensor Parallel, Pipeline Parallel, Context Parallel, Float8, Llama, Pretraining]

---

# TorchTitan - PyTorch Native Distributed LLM Pretraining

## Quick start

TorchTitan is PyTorch's official platform for large-scale LLM pretraining with composable 4D parallelism (FSDP2, TP, PP, CP), achieving 65%+ speedups over baselines on H100 GPUs.

**Installation**:
```bash
# From PyPI (stable)
pip install torchtitan

# From source (latest featu
... [truncated]
--- End skill ---