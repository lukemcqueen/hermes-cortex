"""cost-guard — cron scheduler provider: over-budget fire guard + cost capture.

Sanctioned extension point (cron.provider) that replaces BOTH local core patches
that used to be marker-patched into ~/.hermes/hermes-agent (a SOUL boundary
breach that dirtied the upstream git tree):

  * O6-S1 MAX_COST preflight  → the due-job filter below (was a scheduler.py patch)
  * O1-S3 cron cost capture   → the run wrappers below (was a scheduler.py patch)

Deployed to ``$HERMES_HOME/plugins/cost-guard/`` (the USER plugin dir), which
``plugins/cron_providers`` discovery scans after the bundled tree. Nothing is
written into the hermes-agent git tree, so ``hermes update`` is never dirtied.

Select with:

```yaml
cron:
  provider: cost-guard
  cost_guard:
    enabled: true          # global off-switch; false → pure built-in behavior
    exempt: []             # job names never blocked (work must get done)
    multiplier: 8.0        # daily budget = per-run p95 cap × multiplier
```

How it intercepts (no core file edits):
  - ``cron.scheduler`` imports ``get_due_jobs`` into its module namespace and
    ``tick()`` calls that binding on every cycle. This provider's ``start()``
    temporarily replaces ``cron.scheduler.get_due_jobs`` with a guard-filtering
    wrapper, then runs the built-in tick loop verbatim, and restores the
    original binding on stop.
  - Cost capture wraps ``cron.scheduler.run_job`` (the per-fire entry point):
    after each run it reads the live agent's session token counters and writes
    one row to ``~/.hermes/cron/cron-costs.db`` via the bundled cost_store.
    ``no_agent`` jobs record a zero-cost row.

The sibling helpers ``max_cost_guard.py`` and ``cost_store.py`` are loaded from
THIS directory by file path (not ``cron.*``), so they too live only in the user
plugin dir. Every failure path fails open — the scheduler is never wedged.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from cron.scheduler_provider import InProcessCronScheduler

logger = logging.getLogger("cron.cost_guard_provider")

_HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str):
    """Import a sibling ``.py`` from this plugin dir under a private module name.

    Deliberately NOT ``from .x import`` — the user-plugin package is loaded with
    a synthetic, hyphen-bearing namespace; a plain file-path import avoids any
    reliance on how that name resolves.
    """
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    path = _HERE / filename
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_cost_store = _load_sibling("hc_cron_cost_store", "cost_store.py")
_max_cost_guard = _load_sibling("hc_max_cost_guard", "max_cost_guard.py")


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
        if not job_id or _max_cost_guard is None:
            return False
        import os

        # Config multiplier wins unless the env override is explicit.
        if "MAX_COST_DAILY_MULTIPLIER" not in os.environ:
            os.environ["MAX_COST_DAILY_MULTIPLIER"] = str(_multiplier())
        verdict = _max_cost_guard.should_fire(job_id, job_name=job_name)
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


# ── Cost capture (replaces the scheduler.py cost-tracking patch) ──────────
def _record_cost(job_id: Optional[str], agent, status: str, *, no_agent: bool = False) -> None:
    if not job_id or _cost_store is None:
        return
    try:
        if no_agent:
            _cost_store.record_run(job_id, {
                "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_write_tokens": 0,
                "api_calls": 0, "estimated_cost_usd": 0.0,
                "model": None, "provider": None,
                "no_agent": True, "status": status,
            })
            return
        _cost_store.record_run(job_id, {
            "input_tokens": getattr(agent, "session_input_tokens", 0) or 0,
            "output_tokens": getattr(agent, "session_output_tokens", 0) or 0,
            "cache_read_tokens": getattr(agent, "session_cache_read_tokens", 0) or 0,
            "cache_write_tokens": getattr(agent, "session_cache_write_tokens", 0) or 0,
            "api_calls": getattr(agent, "session_api_calls", 0) or 0,
            "estimated_cost_usd": float(getattr(agent, "session_estimated_cost_usd", 0.0) or 0.0),
            "model": None,
            "provider": None,
            "no_agent": False,
            "status": status,
        })
    except Exception:
        logger.debug("cost-guard: cost record failed (ignored)", exc_info=True)


def _make_run_capture(original: Callable) -> Callable:
    """Wrap cron.scheduler.run_job so each fire records its token usage.

    Tolerant of the callee's exact signature: identifies the agent and job_id
    from positional args first, then kwargs. Fail-open — a capture error never
    changes the run's result.
    """
    import inspect

    try:
        params = list(inspect.signature(original).parameters)
    except (TypeError, ValueError):
        params = []

    def _capturing(*args, **kwargs):
        bound = dict(kwargs)
        for name, value in zip(params, args):
            bound.setdefault(name, value)
        job = bound.get("job") if isinstance(bound.get("job"), dict) else {}
        job_id = bound.get("job_id") or job.get("id") or job.get("job_id")
        no_agent = bool(job.get("no_agent"))
        agent = bound.get("agent")
        try:
            result = original(*args, **kwargs)
        except BaseException:
            try:
                _record_cost(job_id, agent, "failure", no_agent=no_agent)
            except Exception:
                pass
            raise
        try:
            # A no_agent run never constructs an agent; record a zero-cost row.
            _record_cost(job_id, agent, "ok", no_agent=no_agent or agent is None)
        except Exception:
            pass
        return result

    return _capturing


class CostGuardCronScheduler(InProcessCronScheduler):
    """Built-in in-process ticker + per-due-job max-cost guard + cost capture.

    The tick loop is inherited verbatim. The only differences while this
    provider is active:
      * ``cron.scheduler.get_due_jobs`` (the binding ``tick`` calls) is wrapped
        so over-budget jobs never reach dispatch.
      * ``cron.scheduler.run_job`` is wrapped so each fire writes a cost row.
    Both bindings are restored on stop. Disabled config or any guard error →
    the unmodified built-in behavior.
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

        # ── Install the wrappers (restored in finally) ───────────────────
        _orig_get_due = getattr(_scheduler_mod, "get_due_jobs", None)
        _patched_due = False
        if _orig_get_due is not None and _guard_enabled():
            _scheduler_mod.get_due_jobs = _make_due_filter(_orig_get_due)
            _patched_due = True

        _orig_run_job = getattr(_scheduler_mod, "run_job", None)
        _patched_run = False
        if _orig_run_job is not None and _cost_store is not None:
            _scheduler_mod.run_job = _make_run_capture(_orig_run_job)
            _patched_run = True

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
            if _patched_due and _orig_get_due is not None:
                _scheduler_mod.get_due_jobs = _orig_get_due
                logger.debug("cost-guard: restored original get_due_jobs")
            if _patched_run and _orig_run_job is not None:
                _scheduler_mod.run_job = _orig_run_job
                logger.debug("cost-guard: restored original run_job")


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
