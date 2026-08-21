---
name: ollama-setup
description: Install, configure, and manage Ollama on Linux — including sudo-free tarball install, user systemd service, model management, and health verification.
version: 1.1.0
author: agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [ollama, local-llm, embeddings, linux, systemd, setup, inference]
---

# Ollama Setup (Linux)

Install and manage Ollama for local LLM inference and embeddings.

## When to Use

- Setting up a new Linux machine with Ollama for mycortex embeddings
- Installing Ollama without sudo (tarball → `~/.local/bin/` → user systemd)
- Pulling/updating models
- Verifying Ollama health after install or reboot
- Setting up Ollama for use with mycortex (`nomic-embed-text`)
- **Configuring a local model for Hermes cron jobs** (context size, Modelfile tuning)

## Installation Methods

### Method 1: Sudo-free tarball install (preferred for agent-managed hosts)

Works entirely within the user's home directory — no `sudo` needed.

```bash
# 1. Download the tarball (use .tar.zst, not .tgz — .tgz returns 404)
curl -fsL -o /tmp/ollama.tar.zst \
  "https://ollama.com/download/ollama-linux-$(uname -m | sed 's/x86_64/amd64/').tar.zst"

# 2. Extract
mkdir -p /tmp/ollama-extract
tar -xf /tmp/ollama.tar.zst -C /tmp/ollama-extract

# 3. Install binaries
mkdir -p ~/.local/bin ~/.local/lib/ollama
cp /tmp/ollama-extract/bin/ollama ~/.local/bin/
chmod +x ~/.local/bin/ollama
cp -r /tmp/ollama-extract/lib/ollama/* ~/.local/lib/ollama/
chmod +x ~/.local/lib/ollama/llama-server ~/.local/lib/ollama/ollama 2>/dev/null

# Verify
~/.local/bin/ollama --version
```

### Method 2: Official installer (needs sudo)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

## User Systemd Service

Create a user-scoped systemd service binding Ollama to localhost only:

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/ollama.service << 'SVC'
[Unit]
Description=Ollama LLM Server (restricted to localhost)
After=network-online.target

[Service]
ExecStart=/home/$USER/.local/bin/ollama serve
Environment=OLLAMA_HOST=127.0.0.1
Environment=OLLAMA_NUM_THREADS=2    # Limit to 2 threads on CPU-only machines (prevents thermal throttling)
Environment=OLLAMA_KEEP_ALIVE=0     # Unload model immediately after use (reduces idle heat)
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
SVC

> **Thermal mitigation:** `OLLAMA_NUM_THREADS=2` prevents the model runner from saturating all CPU cores (reduces heat output ~60%). `OLLAMA_KEEP_ALIVE=0` unloads the model immediately after each use instead of keeping it loaded for 5 minutes. On CPU-only machines where intermittent LLM use (crons, occasional queries) is the pattern, this keeps the CPU cool between uses. Omit these on GPU machines — they add latency with no thermal benefit.

systemctl --user daemon-reload
systemctl --user enable ollama
systemctl --user start ollama
```

## Verify Service

```bash
for i in $(seq 1 15); do
    curl -s http://127.0.0.1:11434/api/tags >/dev/null \
      && echo "Ollama ready!" && break || sleep 2
done
systemctl --user is-active ollama
```

## Pull Models

```bash
# Embedding model (required for mycortex)
ollama pull nomic-embed-text

# General chat
ollama pull llama3.2:3b

# Code
ollama pull qwen2.5:3b
```

## PATH Setup

Add to `~/.bashrc` or `~/.zshrc` if not already present:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Connect to Hermes Agent

After Ollama is running with models pulled, configure Hermes to use it as a custom provider.

### Option A: Add as custom provider with context size tuning

Edit `~/.hermes/config.yaml` to add a `custom_providers` section with per-model context settings:

```yaml
custom_providers:
  - name: ollama-local
    base_url: http://127.0.0.1:11434/v1
    api_key: ""
    api_mode: chat_completions
    models:
      qwen2.5:3b:
        context_length: 4096
        ollama_num_ctx: 4096
      nomic-embed-text:
        context_length: 8192
```

> **⚠️ Thermal warning — CPU-only machines (especially MacBooks):**
> Do NOT set `context_length: 65536` on CPU-only machines running qwen2.5:3b or similar models. This saturates all CPU cores at 300-400% utilization, pushing the CPU past 90°C on 2014-era MacBooks (i7-4980HQ). The kernel's `intel_powerclamp` module will forcibly inject idle cycles (`idle_inject/[0-7]` in `ps` output), wasting 50% of CPU capacity and causing system halting. Use `context_length: 4096` for CPU-only — the difference in usable code-generation quality is negligible, and the thermal savings are massive (92°C → 59°C). See the `linux-performance-diagnostics` skill (Phase 9) for full diagnostic steps.
> On GPU-equipped machines, 65536 is fine — the GPU handles the attention computation and the CPU stays cool.

Then set cron jobs to use this provider with a model override:

```
hermes cron edit JOB_ID --model qwen2.5:3b --provider custom:ollama-local
```

### Option B: Set as default provider (all sessions use local)

```bash
hermes config set model.default qwen3:4b
hermes config set model.provider local
hermes config set model.base_url http://127.0.0.1:11434/v1
hermes config set model.api_key ollama
```

### Add cloud fallback (recommended)

If the local model is down or too slow, Hermes falls through to a cloud provider:

```bash
hermes config set fallback_providers '[{"provider":"opencode","model":"deepseek-v4-flash-free","base_url":"https://opencode.ai/zen/v1","api_mode":"chat_completions"}]'
```

**Important:** `hermes config set` saves lists/objects as YAML quoted strings, which may corrupt structured fallback config. Verify with `grep -A5 fallback_providers ~/.hermes/config.yaml` — if it's a single quoted line, fix with `sed`:

```bash
sed -i 's/fallback_providers:.*/fallback_providers:\n  - provider: opencode\n    model: deepseek-v4-flash-free\n    base_url: https:\/\/opencode.ai\/zen\/v1\n    api_mode: chat_completions/' ~/.hermes/config.yaml
```

### Model selection in session

- `/model qwen2.5:3b` — switch to local code model
- `/model nomic-embed-text` — switch to embedding model
- `/model deepseek-v4-flash-free` — switch back to cloud
- `/model` (no arg) — interactive picker

## Configuring Model Context Size

When Hermes runs a model through Ollama for tool-calling tasks (cron jobs, code generation), it needs adequate context to support reliable tool use. The required context depends on your hardware:

| Hardware | Recommended context | Notes |
|----------|-------------------|-------|
| GPU-equipped | **65536** (64k) | GPU handles attention computation — CPU stays cool |
| CPU-only (desktop) | **16384-32768** | Monitor temps; 80°C+ means reduce further |
| CPU-only MacBook (pre-2019) | **4096** | 65536 on Haswell i7 hits 92°C+ → kernel throttle |

> **Why 4096 on MacBooks?** LLM inference on CPU is O(n²) in context length. 32768 → 4096 reduces attention computation ~64x. On a 2014 MacBook (i7-4980HQ), this drops CPU usage from 393% to under 100% and temperature from 92°C to 59°C. Without this reduction, `intel_powerclamp` forcibly throttles the CPU, causing system halting.

This requires two separate configuration layers:

### Layer 1: Hermes config (tells Hermes what to request)

```yaml
models:
  qwen2.5:3b:
    context_length: 4096     # Hermes's own token budget
    ollama_num_ctx: 4096     # Passed to Ollama API as num_ctx
```

### Layer 2: Ollama Modelfile (tells Ollama the model's default)

Hermes checks the model's runtime context against its requirement. Even with Layer 1 set, Ollama may load the model with only 32,768 context if the Modelfile default is smaller. Fix by creating a Modelfile:

```bash
ollama create qwen2.5:3b -f <(echo -e "FROM qwen2.5:3b\\nPARAMETER num_ctx 4096")
```

This updates the model's manifest in-place. Verify the Modelfile persisted:

```bash
ollama show qwen2.5:3b --modelfile | grep num_ctx
# Expected: PARAMETER num_ctx 4096
```

**Note:** `ollama ps` still shows `CONTEXT 32768` even after this fix — that's Ollama's initial runtime reservation, not the maximum. Hermes reads the Modelfile capabilities, not `ollama ps`, so the fix is effective despite what `ollama ps` reports.

### When to apply

Apply this to **any** Ollama model used for Hermes cron jobs or interactive sessions that make tool calls. Small models (3B params) and embedding models (<1B params) that only do generation (no tool calling) can keep lower context.

### Cold start warning

The first request after model pull (or after Ollama restart) loads the model into RAM. This takes **5-30 seconds** depending on model size and CPU speed. Subsequent requests are faster because the model stays cached in memory.

## Security Check

Verify localhost-only binding:

```bash
ss -tlnp | grep 11434
# Expected: 127.0.0.1:11434
# NOT:      0.0.0.0:11434
```

## Pitfalls

- **`ollama-linux-amd64.tgz` returns 404**: Use `.tar.zst`, not `.tgz`.
- **OLLAMA_HOST defaults to 0.0.0.0**: Explicitly set `127.0.0.1` in the service to avoid network exposure.
- **User vs system systemd**: User units (`~/.config/systemd/user/`) need no sudo but only run while the user session is active. For persistence across reboots without login, run: `sudo loginctl enable-linger $USER`.
- **mycortex needs llama-server binary**: mycortex's ollama provider runs `llama-server` directly, not through the HTTP API. The full tarball extraction to `~/.local/lib/ollama/` is required — just the `bin/ollama` binary is insufficient.
- **Model pull timeout**: Large models can take 10+ minutes. Use a generous timeout (300s+) when pulling.
- **Service won't start**: Check `journalctl --user -u ollama --no-pager -n 20` for errors. Common issue: missing `~/.local/bin/ollama` binary because the ExecStart path is wrong.
- **Hermes RuntimeError: model context too small**: If Hermes fails with "Ollama loaded `model` with only N tokens of runtime context, but Hermes needs at least 64,000 tokens", the Modelfile `num_ctx` override is missing (Layer 2 above). Running `ollama create` with a Modelfile overriding `num_ctx` fixes it — this is NOT a hardware limitation in most cases. Hermes config's `ollama_num_ctx` alone is insufficient.
- **`ollama ps` shows 32768 after Modelfile fix**: This is expected — the CONTEXT column shows the initial runtime allocation, not the model's maximum. The fix is working if `ollama show <model> --modelfile | grep num_ctx` shows 4096 (or your configured value). Do not re-apply the fix or try other approaches.
- **CPU-only LLM thermal throttling**: Running qwen2.5:3b (or similar) on CPU-only machines with context > 4096 frequently triggers `intel_powerclamp` kernel throttling. Symptoms: `idle_inject/[0-7]` in `ps` output consuming 5-10% CPU each, CPU temp > 80°C, PSI some avg10 > 5%. Fix: reduce context to 4096, limit `OLLAMA_NUM_THREADS=2`, set `OLLAMA_KEEP_ALIVE=0`. See `linux-performance-diagnostics` skill Phase 9 for full diagnostic steps.
- **patch tool writes to whatever path you give it**: If `patch(path=...)` resolves to `~/.hermes-cortex/scripts/` (the deployed copy) instead of `~/hermes-cortex/ops/scripts/` (the repo source), the git repo still has the old values. Always verify with `git diff` after patching repo-tracked files.
- **Ollama exits cleanly (code 0) after model load failure**: When a client closes the connection before the model finishes loading (timeout or disconnect), Ollama logs "client connection closed before llama-server finished loading, aborting load" and may exit with code 0. With `Restart=on-failure`, systemd considers code 0 a clean exit and does NOT restart. Use `Restart=always` instead, and set `RestartSec=30` to avoid rapid restart loops if the failure condition persists.

## References

- **GitHub**: https://github.com/ollama/ollama
- **Model library**: https://ollama.com/library
- **Install script**: https://ollama.com/install.sh
- **Related skills**: `llama-cpp` for GGUF inference, `huggingface-hub` for model discovery
