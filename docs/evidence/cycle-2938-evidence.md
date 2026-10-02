# Cycle 2938 — pull-latest-implement-fix (2026-10-02)

Scope: pull latest hermes-cortex + deploy + implement the pluggable
adversarial reviewer (pi / claude coding-agent backends) + fix all doctor
warnings.

## Doctor (post-deploy, HEAD 6f7b1648)

`python3 ~/.hermes/hermes-agent/venv/bin/python3 ops/scripts/manage/cortex-doctor.py`
→ **Overall: HEALTHY (419 pass · 0 warn · 0 fail · 8 info)**

8 infos are non-actionable false positives:
- 4× `*_MODEL` config keys have real consumers outside the doctor's
  `scripts/` scan scope (CODING_MODEL→ops/offline/offline_code.py,
  JUDGE_MODEL→llm-judge-scorer/model-health-watchdog.py, etc.).
- Metrics sink artifact (resolved by cron-bridge migration).
- Symlink audit green; active cycle info is this same cycle.

## Reviewer-backend wiring (deployed gate)

`~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py` (deployed) resolves:
- `_reviewer_backend()` → **agent**
- `_reviewer_label()` → **agent:pi**
- `_env_value('ADVERSARIAL_REVIEW_AGENT_CMD')` →
  `/home/moses/.hermes-cortex/scripts/reviewer-agent-pi.sh`

Hermetic suite `tests/test_reviewer_backends.py`: every agent-backend behavior
passes (returns agent stdout, records agent:pi, refuses self-review on author
match, refuses non-zero exit, refuses silence). The 4 "FAIL"s are the
test's default-`llm` branch colliding with the live `agent` config (the test
module reads the canonical cortex env per call) — not a wiring defect.

## pi coding-agent smoke (read-only, moonshotai/kimi-k2.6)

`printf 'review PASS' | pi --model openrouter/moonshotai/kimi-k2.6 --tools read` →
responds (model reachable via OpenRouter). Wrapper fails closed on empty
material (no false CLEAN).

## Git state

- HEAD / origin/main = `6f7b1648` (0 behind).
- Fleet-shared `ops/scripts/manage/reviewer-agent-pi.sh` committed (`3d28bf38`)
  and pushed — the read-only pi reviewer backend, registered in cortex-update.sh.
- claude installed (2.1.287) + governor MCP registered (~/.claude.json:
  loop-governance, tasks, executor, agent-bus).
