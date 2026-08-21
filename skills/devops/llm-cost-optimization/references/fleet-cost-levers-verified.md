# Fleet cost levers — verified results (2026-08-21)

Session-verified numbers from the HC gaps cost work. These complement the
main SKILL.md; the SKILL.md sections "The bloat myth" and "Shrink the
per-session tax" summarize them.

## The bloat myth — big prompt numbers are NOT the cost

Measured on Esther (13-day audit + state.db):

- A "26.4M prompt" run = **0.2M fresh input + 26.2M cache-read** (150 API
  calls × growing context, re-sent each turn). At hit prices that's ~$0.18;
  at all-miss it would be $5.81. The cache is doing its job — the number
  scares you but the bill doesn't.
- **Real cost driver = output tokens from iteration loops.** Jobs running to
  the 150-iteration cap emit 90–145K output per run × $0.66/M. Output is
  never cached, so it's the irreducible spend.
- Esther's whole operation measured ~**$0.83/day** (cron $0.38 + interactive
  $0.45) at cache-aware rates — ~$5/day × 6 hosts ≈ half the $10 budget.
  The gap vs the $15–20 billing page was NOT explainable from Esther data;
  the daily digest reconciles it over days (Titus 4× message volume + 4
  hosts unmeasured).

## Levers shipped (all verified)

| Lever | Mechanism | Verified effect |
|-------|-----------|-----------------|
| thinking off | `reasoning_effort: none` on mechanical crons (manifest-pinned) | −54% output tokens on same job (12.8K→5.9K) |
| iteration headroom | `agent.max_turns` 150→250 (aligns with `delegation.max_iterations`) | long jobs finish in one session — no manual reset+paste |
| lean skill index | `agent.coding_context: lean` patch (`install-lean-index.py`) | −19% skill index (−1,681 tok/call), toolset intact |
| per-repo efficiency | `apply-repo-efficiency.py` → AGENTS.md block | behavioral batching/no-re-derivation where devs work |
| peak-hour reduction | backlog-driver 15→8 runs/day; fixer+bus-workday 9→5 | peak LLM runs 19→7/day; no_agent watchdogs cover detection |
| cache-split capture | scheduler patch → `usage_audit.jsonl` cache_read/write tokens | measurement gap closed (needs gateway restart to LOAD) |
| daily digest | `orch-daily-cost-report.py` cron 08:00 KST → Telegram | reads usage_audit + cron-costs + **state.db sessions table** |

## Redactor + timezone gotchas (cost-report code)

- **Redactor masks `Tokens: <value>`** — the secret-redactor treats
  `Tokens:` as a TOKEN-named secret field and masks the value with `***`.
  A cost report line "Tokens: 85M in / 0.6M out" delivers as
  "Tokens: *** in / 0.6M out". Fix: use `Tokens →` (verified passes clean)
  or `Prompt/Comp:` labels. Regression-test against
  `agent.redact.redact_sensitive_text`.
- **Naive-UTC timestamp bug** — `datetime.utcnow().timestamp()` treats the
  naive UTC datetime as LOCAL (+8.6h on KST hosts), mis-filtering sessions.
  Compare epochs directly (`time.time() - days*86400`) or use tz-aware
  datetimes. Caught by a regression test (old-session must be excluded).

## Installer pitfalls (from the seam-rot work)

- **Marker must byte-match inserted content.** A stray prefix in
  `LLM_MARKER` makes the idempotency check never match → false FAIL on
  `--status` every run even though the patch is applied. Verify `new in
  content` after apply.
- **Failure-path patches nest deeper** (16-space vs 12-space indent) — the
  installer's fuzzy markers can collide across success/failure paths
  (`"response_silent": False,` appears in both). Verify with grep.
- **Auto-reapply is the fix for seam rot** — run the installer idempotently
  in cortex-update.sh after every deploy so patches survive `hermes update`.

## Session economics numbers (cache-aware model)

Same session vs new session — the CORRECT model charges re-sent history at
HIT price (it's an identical prefix), not blended:

- 1×150 turns ≈ $0.79; 3×50 ≈ $0.48; 5×30 ≈ $0.45. The long-session premium
  is ~$0.30 of history re-sends at hit price — the cheapest thing you can buy.
- Cache busts are the enemy: one bust every 10 turns turns $0.79 → $2.39 (3×).
- The 67K system prompt is a per-session tax — fewer sessions = fewer cold
  starts; shrinking it (lean index, tool schemas) lowers the tax everywhere.
