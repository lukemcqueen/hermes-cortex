#!/usr/bin/env python3
"""
hermes_models.py — BACK-COMPAT SHIM.

Canonical implementation moved to cortex_lib.models (component-hermes-separation
S1c). This module re-exports cortex_lib.models so existing callers work
unmodified. New code should import from cortex_lib.models directly.
"""
from cortex_lib.models import (  # noqa: F401
    get_model,
    load_models_env,
    _clear_cache,
)

__all__ = ["get_model", "load_models_env", "_clear_cache"]