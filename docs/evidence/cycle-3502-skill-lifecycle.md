# Orch-skill-lifecycle verification evidence

Run: 2026-10-05 morning KST (cron orch-skill-lifecycle), governance cycle 3502.

## What changed

1. `skills/devops/watchdog-alert-design/SKILL.md` — upstreamed (new, v1.0.0)
   from local. Design recipe for debounced health/bus/reachability watchdogs.
2. `skills/devops/watchdog-flapping-diagnostics/SKILL.md` — upstreamed (new,
   v1.0.0) from local. nginx-throttle flapping diagnostics.
3. `skills/devops/systemd-cron-bridge/SKILL.md` — added pitfall: `systemctl
   --user enable` does not start a timer if `timers.target` was already
   reached → enabled-but-inactive, silent never-fire. Fix:
   `systemctl --user start timers.target`.
4. `docs/SKILLS-MANIFEST.md` — regenerated (379 skills).

See commit "skills(lifecycle): upstream watchdog-alert-design +
watchdog-flapping-diagnostics; add systemd enable-but-inactive pitfall" on
remote main (final push: origin main, single squashed commit; the earlier
amended hash was superseded by a rebase onto concurrent remote auto-block
commits, then re-pushed clean).

## Ledger

learning a93afcd7 (`moses: sensor flagged 7 stale mycortex sources; root cause
= ALL 61 cortex-bridge systemd ...`) → **applied**, impact=2, via
`learning-ledger.py set-status` (the ONLY update path). Verified with
`learning-ledger.py list --status applied`.

## Verification (real tool output)

- Doctor: `cortex-doctor.py --quiet` → **✅ Overall: HEALTHY (437 pass,
  0 warn, 0 fail, 8 info)**; final run 438 pass after the flapping skill landed.
- DOGFOOD (`cortex-dogfood.sh --force`; pull → deploy → doctor → verify) →
  **✅ DOGFOOD PASSED — deployed state verified clean** (twice: pre-rebase,
  and again on the rebased commit before push).
- PII gate (`secret-leak-detector.sh`) → exit 0.
- Skill loads: `skill_view` returned success for all three skills in this
  session; fences balanced (systemd-cron-bridge: 2, both watchdog skills: 0);
  all have `version: x.y.z` frontmatter.
- Local deployed copies match repo after dogfood (diff → clean for both
  watchdog skills).