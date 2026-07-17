--- Full content (truncated) ---
---
name: pytorch-lightning
description: High-level PyTorch framework with Trainer class, automatic distributed training (DDP/FSDP/DeepSpeed), callbacks system, and minimal boilerplate. Scales from laptop to supercomputer with same code. Use when you want clean training loops with built-in best practices.
version: 1.0.0
author: Orchestra Research
license: MIT
dependencies: [lightning, torch, transformers]
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [PyTorch Lightning, Training Framework, Distributed Training, DDP, FSDP, DeepSpeed, High-Level API, Callbacks, Best Practices, Scalable]

---

# PyTorch Lightning - High-Level Training Framework

## Quick start

PyTorch Lightning organizes PyTorch code to eliminate boilerplate while maintaining flexibility.

**Installation**:
```bash
pip install lightning
```

**Convert PyTorch to Lightning** (3 steps):

```python
import lightning as L
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

# 
... [truncated]
--- End skill ---