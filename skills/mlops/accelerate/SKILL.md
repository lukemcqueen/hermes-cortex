--- Full content (truncated) ---
---
name: huggingface-accelerate
description: Simplest distributed training API. 4 lines to add distributed support to any PyTorch script. Unified API for DeepSpeed/FSDP/Megatron/DDP. Automatic device placement, mixed precision (FP16/BF16/FP8). Interactive config, single launch command. HuggingFace ecosystem standard.
version: 1.0.0
author: Orchestra Research
license: MIT
dependencies: [accelerate, torch, transformers]
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Distributed Training, HuggingFace, Accelerate, DeepSpeed, FSDP, Mixed Precision, PyTorch, DDP, Unified API, Simple]

---

# HuggingFace Accelerate - Unified Distributed Training

## Quick start

Accelerate simplifies distributed training to 4 lines of code.

**Installation**:
```bash
pip install accelerate
```

**Convert PyTorch script** (4 lines):
```python
import torch
+ from accelerate import Accelerator

+ accelerator = Accelerator()

  model = torch.nn.Transformer()
  optimizer = torch.optim.Adam(mode
... [truncated]
--- End skill ---