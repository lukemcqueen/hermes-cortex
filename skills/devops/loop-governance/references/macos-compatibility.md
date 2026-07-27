# macOS Compatibility

Titus runs macOS. Everything must work there.

## Key Differences from Linux

| Concern | Linux | macOS |
|---------|-------|-------|
| Ollama install | `curl ... | bash` | `brew install ollama` |
| Bash version | 5.x (GNU) | 3.2 (old — avoid `[[ ]]` pitfalls, use POSIX `[ ]`) |
| `grep -oP` | Works (GNU grep) | **DO NOT USE** — no -P flag on macOS. Use `python3 -c "import sys; print(...)"` instead |
| `uname` detection | `uname -s` returns `Linux` | `uname -s` returns `Darwin` — use `[[ "$(uname)" == "Darwin" ]]` to detect macOS in shell scripts |
| `timeout` command | Works (coreutils) | Does not exist. Use `urllib.request.urlopen(timeout=N)` or `brew install coreutils` for `gtimeout` |
| Service manager | systemd | launchd |
| `~/.local/bin/` in PATH | Common convention | Not in PATH by default. Agent must add to ~/.zshrc |
| `du -h` | Works | Works (same BSD-derived) |

## Patterns That Work on Both

```bash
# Python version detection (replaces grep -oP):
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

# Ollama health check (curl works identically):
curl -sf http://localhost:11434/api/tags

# Symlinks:
ln -sf source target

# PATH check:
echo "$PATH" | tr ':' '\n' | grep -q "${HOME}/.local/bin"
```

## Install Flow on macOS

```bash
# 1. Clone
git clone https://github.com/fleet-operator/hermes-cortex.git ~/hermes-cortex

# 2. Run setup (detects macOS, suggests brew)
bash ~/hermes-cortex/core/governance/setup.sh

# 3. If Ollama not found, install:
brew install ollama
ollama pull nomic-embed-text

# 4. Add ~/.local/bin to PATH (add to ~/.zshrc):
export PATH="$HOME/.local/bin:$PATH"

# 5. Verify
bash ~/hermes-cortex/core/governance/verify.sh
```

## Health Monitoring

Health checks (Ollama, DB, nomic model) run inside `system-alert.py`, not as a
separate cron. This script already has macOS/Linux detection:

```python
is_macos = sys.platform == "darwin"
is_linux = sys.platform.startswith("linux")
```

On macOS, the watchdog uses `vm_stat` and `sysctl` for memory monitoring
(guarded by `is_macos`). Loop-governance checks (Ollama, DB) are
platform-agnostic — they use stdlib only.

## Ollama Auto-Restart on macOS

```bash
ollama serve &>/dev/null &
# Retry up to 10 seconds (macOS starts slower)
for i in 1 2 3 4 5; do
  sleep 2
  curl -sf http://localhost:11434/api/tags &>/dev/null && break
done
```