"""fleet_lib — neutral Hermes-independent client library for fleet components.

Separates our components from the Hermes runtime (component-hermes-separation.md
scope 1): every module here resolves with zero Hermes import. The legacy
`hermes_*` modules (hermes_tz, hermes_paths, hermes_models, hermes_tools) become
thin re-export shims of these canonical modules so existing callers keep working
unmodified.

This package was renamed from `fleet_lib` (2026-11-06, cortex->fleet short-name
sweep). The old name remains as a one-release re-export shim
(`ops/scripts/fleet_lib/`) so undeployed/legacy callers keep resolving.

Imports resolve from `ops/scripts/` being on sys.path (see fleet_lib.paths.
ensure_scripts_path). This package is Hermes-agnostic by rule: no `import hermes*`
is allowed inside fleet_lib.
"""

__all__ = []