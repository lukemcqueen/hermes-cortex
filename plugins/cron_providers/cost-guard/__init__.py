"""cost-guard — cron scheduler provider that blocks over-budget fires.

Sanctioned extension point (cron.provider) replacing the O6-S1 local patch to
cron/scheduler.py + tools/cronjob_tools.py. Select with:

```yaml
cron:
  provider: cost-guard
  cost_guard:
    enabled: true          # global off-switch; false → pure built-in behavior
    exempt: []             # job names never blocked (work must get done)
    multiplier: 8.0        # daily budget = per-run p95 cap × multiplier
```

How it intercepts (no core file edits):
  - ``cron.scheduler`` imports ``get_due_jobs`` into its module namespace
    (cron/scheduler.py:648) and ``tick()`` calls that binding on every cycle.
  - This provider's ``start()`` temporarily replaces
    ``cron.scheduler.get_due_jobs`` with a guard-filtering wrapper, runs the
    built-in tick loop verbatim, and restores the original binding on stop.
  - Every due job is checked by ``max_cost_guard.should_fire()``; blocked
    jobs are removed from the due set (left due — the spend brake skips the
    fire, it does not reschedule it), so the built-in dispatch never sees
    them. Fail-open everywhere.

Why a provider plugin instead of a scheduler.py patch: this is the sanctioned
surface (CronScheduler ABC + plugins/cron_providers discovery), survives
`hermes update` with zero re-apply, and can be disabled by config alone.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from cron.scheduler_provider import InProcessCronScheduler

logger = logging.getLogger("cron.cost_guard_provider")


def _cfg() -> Dict[str, Any]:
    """cron.cost_guard config block; {} on any failure (fail-open)."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        cron_cfg = cfg.get("cron", {}) if isinstance(cfg, dict) else {}
        guard_cfg = cron_cfg.get("cost_guard", {}) if isinstance(cron_cfg, dict) else {}
        return guard_cfg if isinstance(guard_cfg, dict) else {}
    except Exception as exc:
        logger.debug("cost-guard config read failed (fail open): %s", exc)
        return {}


def _guard_enabled() -> bool:
    try:
        return bool(_cfg().get("enabled", True))
    except Exception as exc:
        logger.debug("cost-guard enabled read failed (fail open): %s", exc)
        return True  # fail open


def _exempt_names() -> set:
    try:
        raw = _cfg().get("exempt", []) or []
        return {str(x).strip() for x in raw if str(x).strip()}
    except Exception as exc:
        logger.debug("cost-guard exempt read failed (fail open): %s", exc)
        return set()


def _multiplier() -> float:
    try:
        return float(_cfg().get("multiplier", 8.0) or 8.0)
    except (TypeError, ValueError) as exc:
        logger.debug("cost-guard multiplier read failed (fail open): %s", exc)
        return 8.0


def _should_block(job: Dict[str, Any]) -> bool:
    """True when this job must not fire this tick. Fail-open → False."""
    try:
        if not _guard_enabled():
            return False
        job_name = str(job.get("name") or "")
        if job_name in _exempt_names():
            return False
        job_id = job.get("id") or job.get("job_id")
        if not job_id:
            return False
        import os

        from cron.max_cost_guard import should_fire

        # Config multiplier wins unless the env override is explicit.
        if "MAX_COST_DAILY_MULTIPLIER" not in os.environ:
            os.environ["MAX_COST_DAILY_MULTIPLIER"] = str(_multiplier())
        verdict = should_fire(job_id, job_name=job_name)
        return verdict.get("decision") == "block"
    except Exception as exc:  # fail open — never wedge the scheduler
        logger.warning("cost-guard should_block raised (fail open): %s", exc)
        return False


def _make_due_filter(original: Callable[[], List[Dict[str, Any]]]) -> Callable:
    """Wrap get_due_jobs: remove over-budget jobs from the due set."""

    def _guarded_due_jobs() -> List[Dict[str, Any]]:
        try:
            due = original()
        except Exception:
            # Propagate the original error unchanged — the caller's tick loop
            # handles it (heartbeat/backoff); never swallow a due-jobs read
            # failure or the scheduler would silently stop seeing jobs.
            raise
        if not due:
            return due
        try:
            blocked = [j for j in due if _should_block(j)]
        except Exception as exc:
            logger.error("cost-guard filter failed (dispatching all due): %s", exc)
            return due
        if blocked:
            logger.warning(
                "cost-guard blocked %d over-budget job(s): %s",
                len(blocked),
                [j.get("name") or j.get("id") for j in blocked],
            )
            blocked_ids = {j.get("id") for j in blocked}
            return [j for j in due if j.get("id") not in blocked_ids]
        return due

    return _guarded_due_jobs


class CostGuardCronScheduler(InProcessCronScheduler):
    """Built-in in-process ticker + per-due-job max-cost guard.

    The tick loop is inherited verbatim. The only difference: while this
    provider is active, ``cron.scheduler.get_due_jobs`` (the binding the
    built-in ``tick`` calls) is wrapped so over-budget jobs never reach
    dispatch. Disabled config or any guard error → the unmodified built-in
    due set is dispatched.
    """

    @property
    def name(self) -> str:
        return "cost-guard"

    def start(self, stop_event, *, adapters=None, loop=None, interval=60,
              can_dispatch=None, profile_homes=None):
        import logging

        from cron import scheduler as _scheduler_mod
        from cron.jobs import (
            clear_ticker_error,
            record_ticker_error,
            record_ticker_heartbeat,
        )

        logger = logging.getLogger("cron.scheduler_provider")
        if profile_homes:
            # Multiplex profiles: delegate to the built-in unchanged. The
            # guard would need per-profile cost stores; keep it simple and
            # safe — multiplexed mode is unguarded (documented).
            return super().start(
                stop_event,
                adapters=adapters,
                loop=loop,
                interval=interval,
                can_dispatch=can_dispatch,
                profile_homes=profile_homes,
            )

        if not _guard_enabled():
            logger.info("cost-guard provider: disabled by config — built-in behavior")
        else:
            logger.info(
                "cost-guard provider active (exempt=%s, multiplier=%s)",
                sorted(_exempt_names()),
                _multiplier(),
            )

        # ── Install the due-job filter (restored in finally) ─────────────
        _orig_get_due = getattr(_scheduler_mod, "get_due_jobs", None)
        _patched = False
        if _orig_get_due is not None and _guard_enabled():
            _scheduler_mod.get_due_jobs = _make_due_filter(_orig_get_due)
            _patched = True

        try:
            recovered = self.recover_interrupted()
            if recovered:
                logger.warning(
                    "Marked %d interrupted cron execution(s) unknown after restart",
                    recovered,
                )
            record_ticker_heartbeat()

            consecutive_failures = 0
            while not stop_event.is_set():
                ok = False
                try:
                    if can_dispatch is not None and not can_dispatch():
                        logger.debug(
                            "Cron dispatch paused while gateway drains existing work"
                        )
                    else:
                        # The built-in tick loop body — unchanged. It calls
                        # cron.scheduler.get_due_jobs (now filtered) and
                        # dispatches whatever remains.
                        from cron.scheduler import tick as cron_tick

                        cron_tick(
                            verbose=False,
                            adapters=adapters,
                            loop=loop,
                            sync=False,
                            can_dispatch=can_dispatch,
                        )
                    ok = True
                except BaseException as e:
                    logger.error("Cron tick error: %s", e, exc_info=True)
                    try:
                        record_ticker_error(f"{type(e).__name__}: {e}")
                    except Exception as _rec_exc:
                        logger.debug("record_ticker_error failed: %s", _rec_exc)
                    consecutive_failures = _note_failure(e, consecutive_failures)
                record_ticker_heartbeat(success=ok)
                if ok:
                    try:
                        clear_ticker_error()
                    except Exception as _clear_exc:
                        logger.debug("clear_ticker_error failed: %s", _clear_exc)
                    consecutive_failures = 0
                stop_event.wait(_backoff_seconds(interval, consecutive_failures))
        finally:
            if _patched and _orig_get_due is not None:
                _scheduler_mod.get_due_jobs = _orig_get_due
                logger.debug("cost-guard: restored original get_due_jobs")


def _backoff_seconds(interval: float, consecutive_failures: int) -> float:
    try:
        from cron.scheduler_provider import _backoff_wait_seconds

        return _backoff_wait_seconds(interval, consecutive_failures)
    except Exception:
        return float(interval)


def _note_failure(exc: BaseException, consecutive_failures: int) -> int:
    try:
        from cron.scheduler_provider import _note_tick_failure

        return _note_tick_failure(exc, consecutive_failures)
    except Exception:
        return consecutive_failures + 1


def register(ctx) -> None:
    """Plugin registration entry point (plugins/cron_providers discovery)."""
    ctx.register_cron_scheduler(CostGuardCronScheduler())
