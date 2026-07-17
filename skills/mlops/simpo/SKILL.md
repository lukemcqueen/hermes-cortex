--- Full content (truncated) ---
---
name: simpo-training
description: Simple Preference Optimization for LLM alignment. Reference-free alternative to DPO with better performance (+6.4 points on AlpacaEval 2.0). No reference model needed, more efficient than DPO. Use for preference alignment when want simpler, faster training than DPO/PPO.
version: 1.0.0
author: Orchestra Research
license: MIT
dependencies: [torch, transformers, datasets, trl, accelerate]
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Post-Training, SimPO, Preference Optimization, Alignment, DPO Alternative, Reference-Free, LLM Alignment, Efficient Training]

---

# SimPO - Simple Preference Optimization

## Quick start

SimPO is a reference-free preference optimization method that outperforms DPO without needing a reference model.

**Installation**:
```bash
# Create environment
conda create -n simpo python=3.10 && conda activate simpo

# Install PyTorch 2.2.2
# Visit: https://pytorch.org/get-started/locally/

# Install alignment-ha
... [truncated]
--- End skill ---