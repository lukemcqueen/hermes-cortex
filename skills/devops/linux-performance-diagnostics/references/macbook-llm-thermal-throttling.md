# MacBook LLM Thermal Throttling — Full Session Trace

## System Profile

MacBook (2014) — applesmc | i7-4980HQ @ 2.80GHz (4C/8T) | 15Gi RAM | Intel integrated GPU | schedutil + intel_cpufreq (passive)

## Heat Source

`qwen2.5-coder:3b` via Ollama at 32768 context on **all 8 threads**, keep-alive=300s:
- CPU: 276-393% (all cores saturated) | RSS: 3.2GiB

## Diagnostic Peak

| Signal | Value | Meaning |
|--------|-------|---------|
| CPU temp | 92°C (threshold 84°C) | **Overheating** |
| idle_inject/[0-7] | 6.4% CPU each | Kernel throttle (powerclamp) |
| PSI some avg10 | 30.72% | Tasks stalled |
| dmesg | "Start idle injection" at +226s | Triggered 4 min after boot |

## The Wrong Fix (first attempt)

Reduced context 65536→4096. Dropped temps to 54°C but:
- Broke Hermes 64k standard — SOUL.md is 34KB
- Crons would silently truncate long inputs
- Missed root cause entirely

## The Correct Fix

**Thread limit + keep-alive, NOT context reduction:**

```ini
Environment=OLLAMA_NUM_THREADS=2
Environment=OLLAMA_KEEP_ALIVE=0
```

Verification with 65536 context: **58°C** (vs 54°C at 4096). Context size barely affects heat.

## Results

| Metric | Before (8 threads, keep=300s, 32k) | After (2 threads, keep=0, 64k) |
|--------|-------------------------------------|--------------------------------|
| Temp | 92°C | 58°C |
| Context | 32768 (broken standard) | 65536 (restored) |
| PSI | 30.7% | 0.55% |
| Powerclamp | Active | Stopped |

## Key Lessons

1. **Thread count dominates heat**, not context size. Context affects KV cache memory; threads determine watt draw.
2. **Never change a system parameter without checking ALL consumers.** 64k existed because SOUL.md is 34KB.
3. **When user says "check again," enumerate everything.** Full audit revealed 42 jobs, 4 using local model.
4. **Keep-alive = residual heat.** `OLLAMA_KEEP_ALIVE=0` prevents sustained warmth between requests.
5. **PSI reveals what `top` hides.** 58% "idle" was powerclamp-forced, with 30% real contention.
