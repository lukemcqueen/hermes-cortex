# Computer Specs Guide — Hermes Cortex

This guide helps you choose the right local LLM model and offline content for your
computer's hardware. Hermes Cortex runs on anything from an 8 GB MacBook to a
desktop workstation — the difference is which models and content sets make sense.

## Quick Reference

| Hardware Tier | RAM | Recommended Model | ZIM Content | Offline Quality |
|---|---|---|---|---|
| **Entry** | 8 GB | Qwen3:4b, Gemma3:1b | Travel bundle (~6 GB) | Good — enough for travel/education |
| **Standard** | 16 GB | Qwen3:8b, DeepSeek-R1:7b | All bundles (~10 GB) | Great — can run everything |
| **Performance** | 32 GB | Qwen3:14b, DeepSeek-Coder:14b | All + Wikipedia mini (~22 GB) | Excellent — full knowledge |
| **Workstation** | 64+ GB | Qwen3:32b, Llama3:70b | Everything (~40+ GB) | Maximum — near-internet quality |

## Model Selection by Hardware

### 8 GB RAM (Entry — MacBook Air/Intel)

Best models (choose one):
- **Qwen3:4b** (~2.5 GB) — Best all-rounder. Code, reasoning, general knowledge
- **Gemma3:1b** (~800 MB) — Tiny but capable. Fast responses
- **DeepSeek-R1:1.5b** (~1.1 GB) — Good reasoning for its size

Embedding model (always needed for web-cache + gbrain):
- **nomic-embed-text** (~300 MB) — 768-dim, works on everything

**Strategy**: Keep Ollama RAM budget to ~3 GB. Run Qwen3:4b + nomic-embed-text simultaneously.
Load ZIM content sparingly — kiwix-serve Docker adds ~500 MB overhead.

### 16 GB RAM (Standard — MacBook Pro M1/M2/M3)

Best models (choose one):
- **Qwen3:8b** (~4.9 GB) — Strong reasoning, good code
- **DeepSeek-R1:7b** (~4.5 GB) — Excellent reasoning
- **Gemma3:4b** (~2.5 GB) — Fast, good all-rounder
- **Mistral-Nemo** (~7 GB) — Best quality if you have room

**Strategy**: Keep Ollama RAM budget to ~6 GB. Run Qwen3:8b + nomic-embed-text.
Load full travel bundle (~6 GB) comfortably. You can keep Docker + Ollama + browser open.

### 32 GB RAM (Performance — MacBook Pro M4 Max / Mac Mini)

Best models (choose one):
- **Qwen3:14b** (~8.5 GB) — Near GPT-3.5 quality
- **DeepSeek-Coder:14b** (~8.5 GB) — Best for code
- **Llama3.1:8b** (~4.9 GB) — Fast, reliable
- **Phi-4:14b** (~8.5 GB) — Good reasoning

**Strategy**: Run a 14B model comfortably. Load Wikipedia mini (~12 GB) for full encyclopedia
coverage. Keep other apps running with no swap pressure.

### 64+ GB RAM (Workstation — Mac Pro / PC)

Best models:
- **Qwen3:32b** (~19 GB) — Near GPT-4 level reasoning
- **Llama3.3:70b** (~40 GB) — Frontier model quality
- **DeepSeek-R1:32b** (~19 GB) — Excellent reasoning

**Strategy**: Run a 32B+ model. Load everything — full Wikipedia (nopic, ~52 GB) if you have
disk space. Models this large benefit from GPU acceleration (NVIDIA CUDA or Metal on Apple
Silicon).

## Disk Space Guide

| Content | Size | Notes |
|---|---|---|
| Ollama models (Qwen3:4b + nomic-embed-text) | ~3 GB | Required minimum |
| Travel bundle (Wikivoyage + WikiMed + Simple Wiki) | ~6 GB | Recommended for all users |
| Education bundle (Simple Wiki + Wikibooks) | ~5 GB | Kid learning |
| Build bundle (Simple Wiki + Wikibooks + Wiktionary) | ~7 GB | Development offline |
| All bundles | ~10 GB | Everything but full Wikipedia |
| Full Wikipedia mini | ~12 GB | Best encyclopedia coverage |
| Full Wikipedia nopic | ~52 GB | Complete, text-only |
| Full Wikipedia maxi | ~124 GB | Complete with images |

**Recommendation by use case:**

| Use Case | Minimum | Recommended |
|---|---|---|
| Jungle travel | 6 GB (travel bundle) | 10 GB (all bundles) |
| Kid education | 5 GB (education bundle) | 10 GB (all bundles) |
| Software development | 7 GB (build bundle) | 19 GB (build + Wikipedia mini) |
| Everything | 10 GB (all bundles) | 22 GB (all + Wikipedia mini) |

## Detection Script

Save this as `check-specs.sh` to auto-detect capabilities:

```bash
#!/bin/bash
# Hermes Cortex — Hardware Detection
echo "=== Hermes Cortex — System Specs ==="
echo ""

# OS
echo "OS: $(uname -srm)"
if [[ "$(uname)" == "Darwin" ]]; then
    echo "Model: $(sysctl -n hw.model 2>/dev/null || echo 'unknown')"
    echo "Chip: $(sysctl -n machdep.cpu.brand_string 2>/dev/null || sysctl -n hw.machine)"
fi

# RAM
total_ram=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
ram_gb=$((total_ram / 1073741824))
echo "RAM: ${ram_gb} GB"

# Disk space
zim_dir="${HOME}/offline/zim"
if [[ -d "$zim_dir" ]]; then
    echo "ZIM content: $(du -sh "$zim_dir" 2>/dev/null | cut -f1)"
fi

# Free disk
free_disk=$(df -h / | awk 'NR==2 {print $4}')
echo "Free disk: ${free_disk}"

# Ollama models
if command -v ollama &>/dev/null; then
    echo ""
    echo "=== Ollama Models ==="
    ollama list 2>/dev/null | tail -n +2 || echo "  (no models)"
fi

# Recommendation
echo ""
echo "=== Recommendation ==="
if [[ $ram_gb -le 8 ]]; then
    echo "Model: Qwen3:4b (or Gemma3:1b if RAM-constrained)"
    echo "Bundle: Travel (~6 GB)"
    echo "Cache: Keep Ollama budget to ~3 GB"
elif [[ $ram_gb -le 16 ]]; then
    echo "Model: Qwen3:8b (or DeepSeek-R1:7b)"
    echo "Bundle: All bundles (~10 GB)"
    echo "Cache: Full ZIM content + Docker"
elif [[ $ram_gb -le 32 ]]; then
    echo "Model: Qwen3:14b (or DeepSeek-Coder:14b)"
    echo "Bundle: All bundles + Wikipedia mini (~22 GB)"
    echo "Cache: Everything"
else
    echo "Model: Qwen3:32b or larger"
    echo "Bundle: Everything including full Wikipedia"
    echo "Cache: Maximum configuration"
fi
```

## Verifying Your Setup

```bash
# After install, run:
hermes-cortex/offline/prep-offline.sh

# Check system status
offline_knowledge stats

# Expected output will show:
# ✅ Web Cache — ready
# ✅ kiwix-serve — running (or stopped if no ZIM files yet)
# ✅ gbrain — ready
# 📚 ZIM Content — N files, X GB total
```
