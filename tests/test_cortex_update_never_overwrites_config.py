#!/usr/bin/env python3
"""Regression test: cortex-update.sh must NEVER auto-run Hermes-config writers.

2026-09-08 fleet-wide clobber (esther/joseph/kustos/gisu): cortex-update.sh
auto-ran install-fallback-providers.py + install-model-default.sh on every
sync/deploy, overwriting operator-owned ~/.hermes/config.yaml
model.default + fallback_providers. A per-host CORTEX_SKIP_MODEL_CONVERGENCE
flag in gitignored .env only protected moses — every other agent was clobbered.

Root fix: the two config-writing scripts are registered for MANUAL operator
use only and are NEVER invoked by cortex-update.sh. ~/.hermes/config.yaml
model keys are operator-owned Hermes runtime config, not cortex cron config.

This test fails if cortex-update.sh ever auto-invokes either script again.
"""
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "ops" / "scripts" / "cortex-update.sh"

# Scripts that WRITE operator-owned ~/.hermes/config.yaml model/fallback keys.
_CONFIG_WRITERS = (
    "install-fallback-providers.py",
    "install-model-default.sh",
)


def _script_text() -> str:
    return _SCRIPT.read_text()


def _is_register_line(line: str, writer: str) -> bool:
    """True only for the `register ...` deployment line, not an invocation."""
    return ("register" in line and writer in line)


def test_config_writers_never_auto_invoked_in_cortex_update():
    """cortex-update.sh must not run the writers in its main body.

    Each writer may appear only on its `register` deployment line (which
    copies the script to ~/.hermes-cortex/scripts/ for manual use) — never
    as a python3/bash invocation that executes it.
    """
    text = _script_text()
    for writer in _CONFIG_WRITERS:
        # Any non-register occurrence means it's being invoked/run somewhere.
        offending = [
            i
            for i, line in enumerate(text.splitlines(), 1)
            if writer in line and not _is_register_line(line, writer)
        ]
        assert not offending, (
            f"cortex-update.sh line(s) {offending} reference {writer} outside a "
            "register line — config writers must be MANUAL-ONLY, never auto-run. "
            "This would overwrite operator-owned ~/.hermes/config.yaml model/"
            "fallback keys on every agent sync (2026-09-08 fleet clobber)."
        )


def test_no_model_convergence_skip_flag_logic_remains():
    """The CORTEX_SKIP_MODEL_CONVERGENCE opt-out is gone (removed with the calls)."""
    text = _script_text()
    assert "CORTEX_SKIP_MODEL_CONVERGENCE" not in text, (
        "Stale CORTEX_SKIP_MODEL_CONVERGENCE logic remains — the convergence "
        "calls were removed outright; the per-host skip flag is a vestige of "
        "the opt-out anti-pattern and must not linger."
    )
