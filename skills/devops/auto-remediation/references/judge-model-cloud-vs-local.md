# JUDGE_MODEL: Cloud API vs Local Ollama Model

## Error Signal

```
[YYYY-MM-DD HH:MM KST] model-health-watchdog: ❌ deepseek-v4-flash — MISSING
     Purpose: LLM-as-Judge scoring (configured as judge model)
[YYYY-MM-DD HH:MM KST] model-health-watchdog: Some required models are missing. To install:
  ollama pull deepseek-v4-flash
```

Meanwhile `ollama list` shows only local models:

```
NAME                     ID              SIZE      MODIFIED     
qwen2.5-coder:3b         f72c60cabf62    1.9 GB    15 hours ago    
nomic-embed-text:v1.5    0a109f422b47    274 MB    40 hours ago
```

## Root Cause

`~/hermes-cortex/.env` has `JUDGE_MODEL=deepseek-v4-flash` — a cloud API model name
that was copied from the orchestrator's `LLM_CRON_MODEL` setting. The watchdog
reads this config via `hermes_models.get_model("JUDGE_MODEL", ...)` and correctly
reports it missing from Ollama. But `deepseek-v4-flash` (and similar: `gpt-4o`,
`claude-sonnet`, `gemini-pro`) **should never be in Ollama** — they're cloud API models.

## Fix

Change `JUDGE_MODEL` in `~/hermes-cortex/.env` to the actual local Ollama judge model:

```bash
# Before
JUDGE_MODEL=deepseek-v4-flash

# After
JUDGE_MODEL=qwen2.5-coder:3b
```

## How Config Resolution Works

`hermes_models.py` resolves model names in this priority:
1. `~/hermes-cortex/.env` (the repo config file, **not** the `~/.hermes-cortex/.env` symlink)
2. Runtime env var (`os.environ`)
3. `~/.hermes/models.env` (legacy fallback)
4. Hardcoded default

## Verification

```bash
# 1. Confirm the config
grep JUDGE_MODEL ~/hermes-cortex/.env
# → JUDGE_MODEL=qwen2.5-coder:3b

# 2. Run the watchdog
python3 ~/.hermes/scripts/model-health-watchdog.py --verbose
# → ✅ nomic-embed-text:v1.5
# → ✅ qwen2.5-coder:3b
# → exit 0

# 3. Verify runtime resolution resolves correctly
python3 -c "
import os; os.environ.pop('JUDGE_MODEL', None)
import sys; sys.path.insert(0, '$HOME/.hermes/scripts')
from hermes_models import get_model
j = get_model('JUDGE_MODEL', 'qwen2.5-coder:3b')
assert j == 'qwen2.5-coder:3b'
print(f'PASS: JUDGE_MODEL={j}')
"
```

## Config-File-Only Verification Gate Note

`.env` files are not Python — py_compile and pytest do not apply.
The verification gate must be satisfied with:
- **Config content check**: `grep KEY file.env`
- **Dependent script test**: run the consumer script that reads the config
- **AST resolution check**: walk `hermes_models.py` to confirm the config path
