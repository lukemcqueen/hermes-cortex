--- Full content (truncated) ---
---
name: fine-tuning-with-trl
description: "TRL: SFT, DPO, PPO, GRPO, reward modeling for LLM RLHF."
version: 1.0.0
author: Orchestra Research
license: MIT
dependencies: [trl, transformers, datasets, peft, accelerate, torch]
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Post-Training, TRL, Reinforcement Learning, Fine-Tuning, SFT, DPO, PPO, GRPO, RLHF, Preference Alignment, HuggingFace]

---

# TRL - Transformer Reinforcement Learning

## Quick start

TRL provides post-training methods for aligning language models with human preferences.

**Installation**:
```bash
pip install trl transformers datasets peft accelerate
```

**Supervised Fine-Tuning** (instruction tuning):
```python
from trl import SFTTrainer

trainer = SFTTrainer(
    model="Qwen/Qwen2.5-0.5B",
    train_dataset=dataset,  # Prompt-completion pairs
)
trainer.train()
```

**DPO** (align with preferences):
```python
from trl import DPOTrainer, DPOConfig

config = DPOConfig(output_dir="model-dpo", beta=0
... [truncated]
--- End skill ---