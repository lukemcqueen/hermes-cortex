--- Full content (truncated) ---
---
name: optimizing-attention-flash
description: Optimizes transformer attention with Flash Attention for 2-4x speedup and 10-20x memory reduction. Use when training/running transformers with long sequences (>512 tokens), encountering GPU memory issues with attention, or need faster inference. Supports PyTorch native SDPA, flash-attn library, H100 FP8, and sliding window attention.
version: 1.0.0
author: Orchestra Research
license: MIT
dependencies: [flash-attn, torch, transformers]
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Optimization, Flash Attention, Attention Optimization, Memory Efficiency, Speed Optimization, Long Context, PyTorch, SDPA, H100, FP8, Transformers]

---

# Flash Attention - Fast Memory-Efficient Attention

## Quick start

Flash Attention provides 2-4x speedup and 10-20x memory reduction for transformer attention through IO-aware tiling and recomputation.

**PyTorch native (easiest, PyTorch 2.2+)**:
```python
import torch
import torch.nn.functional a
... [truncated]
--- End skill ---