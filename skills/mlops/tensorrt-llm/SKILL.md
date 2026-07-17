--- Full content (truncated) ---
---
name: tensorrt-llm
description: Optimizes LLM inference with NVIDIA TensorRT for maximum throughput and lowest latency. Use for production deployment on NVIDIA GPUs (A100/H100), when you need 10-100x faster inference than PyTorch, or for serving models with quantization (FP8/INT4), in-flight batching, and multi-GPU scaling.
version: 1.0.0
author: Orchestra Research
license: MIT
dependencies: [tensorrt-llm, torch]
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Inference Serving, TensorRT-LLM, NVIDIA, Inference Optimization, High Throughput, Low Latency, Production, FP8, INT4, In-Flight Batching, Multi-GPU]

---

# TensorRT-LLM

NVIDIA's open-source library for optimizing LLM inference with state-of-the-art performance on NVIDIA GPUs.

## When to use TensorRT-LLM

**Use TensorRT-LLM when:**
- Deploying on NVIDIA GPUs (A100, H100, GB200)
- Need maximum throughput (24,000+ tokens/sec on Llama 3)
- Require low latency for real-time applications
- Working with quantized models 
... [truncated]
--- End skill ---