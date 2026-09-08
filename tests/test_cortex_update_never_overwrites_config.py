#!/usr/bin/env python3
"""Regression test: cortex-update.sh must NEVER auto-write operator-owned config.

2026-09-08 fleet-wide clobber (esther/joseph/kustos/gisu): cortex-update.sh
auto-ran install-fallback-providers.py + install-model-default.sh on every
sync/deploy, overwriting operator-owned ~/.hermes/config.yaml
model.default + fallback_providers. A per-host CORTEX_SKIP_MODEL_CONVERGENCE
flag in gitignored .env only protected moses — every other agent was clobbered.

2026-09-09: both writer scripts were removed entirely (source, register lines,
deployed copies) after d709d752 de-registered their auto-run. ~/.hermes/config.yaml
model keys are operator-owned Hermes runtime config (set via `hermes config set`),
resolved at runtime by upstream Hermes — cortex ships no tool that writes them.

This test fails if cortex-update.sh ever references either removed writer again
(via register OR invocation) — a re-add is a re-introduction of the clobber class.
"""
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "ops" / "scripts" / "cortex-update.sh"

# Scripts that WRITE operator-owned ~/.hermes/config.yaml model/fallback keys.
# Removed 2026-09-09 — must never be re-introduced in any form.
_REMOVED_CONFIG_WRITERS = (
    "install-fallback-providers.py",
    "install-model-default.sh",
)


def _script_text() -> str:
    return _SCRIPT.read_text()


def test_removed_config_writers_absent_from_cortex_update():
    """Neither removed writer may be referenced in cortex-update.sh at all."""
    text = _script_text()
    offending = [
        i
        for i, line in enumerate(text.splitlines(), 1)
        if any(writer in line for writer in _REMOVED_CONFIG_WRITERS)
    ]
    assert not offending, (
        f"cortex-update.sh line(s) {offending} reference a removed config-writer "
        f"({', '.join(_REMOVED_CONFIG_WRITERS)}) — these were deleted 2026-09-09 "
        "because they overwrote operator-owned ~/.hermes/config.yaml model/fallback "
        "keys on every agent sync (2026-09-08 fleet clobber). Re-adding one in any "
        "form (register OR invocation) re-introduces the clobber class."
    )


def test_no_model_convergence_skip_flag_logic_remains():
    """The CORTEX_SKIP_MODEL_CONVERGENCE opt-out is gone (removed with the calls)."""
    text = _script_text()
    assert "CORTEX_SKIP_MODEL_CONVERGENCE" not in text, (
        "Stale CORTEX_SKIP_MODEL_CONVERGENCE logic remains — the convergence "
        "calls were removed outright; the per-host skip flag is a vestige of "
        "the opt-out anti-pattern and must not linger."
    )
