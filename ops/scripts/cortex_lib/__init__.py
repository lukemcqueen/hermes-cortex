"""cortex_lib — neutral Hermes-independent client library for fleet components.

Separates our components from the Hermes runtime (component-hermes-separation.md
scope 1): every module here resolves with zero Hermes import. The legacy
`hermes_*` modules (hermes_tz, hermes_paths, hermes_models, hermes_tools) become
thin re-export shims of these canonical modules so existing callers keep working
unmodified.

Imports resolve from `ops/scripts/` being on sys.path (see cortex_lib.paths.
ensure_scripts_path / hermes_paths). This package is Hermes-agnostic by rule:
no `import hermes*` is allowed inside cortex_lib.
"""

__all__ = []