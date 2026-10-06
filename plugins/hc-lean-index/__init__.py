"""hc-lean-index — add a distinct ``lean`` coding-context mode.

Replaces the local core patch that used to be marker-patched into
``~/.hermes/hermes-agent/agent/coding_context.py`` (a SOUL boundary breach that
dirtied the upstream git tree). Installed to ``$HERMES_HOME/plugins/hc-lean-index/``.

Background: upstream folds ``agent.coding_context: lean`` into ``focus``. Focus
only demotes on cli/tui/desktop AND collapses the toolset to "coding" — so a
telegram ops agent never gets the lean index at all. This plugin keeps ``lean``
a DISTINCT mode that demotes the non-fleet skill categories to names-only on
ANY platform, WITHOUT the focus-mode toolset collapse.

Safety contract is identical to upstream focus: demoted, never hidden — every
category name stays listed and loadable via skill_view / skills_list.

No core files are edited: ``agent/system_prompt.py::_skills_prompt`` imports
``coding_compact_skill_categories`` at CALL time, so replacing the module
attribute takes effect for every subsequent prompt build in this process.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("plugins.hc_lean_index")

# Marketing / creative / consumer categories this ops fleet never loads in a
# session — their descriptions are noise that inflate every prompt's skill
# index. Mirrors the fleet's historical core patch exactly.
_LEAN_INDEX_CATEGORIES = (
    "apple", "communication", "cooking", "creative", "email", "finance", "gaming", "gifs", "health", "media",
    "music", "note-taking", "productivity", "shopping", "smart-home", "social-media", "travel", "yuanbao",
    "ads", "app-store-optimization", "brand-guidelines", "brand-intelligence",
    "campaign-analytics", "cold-email", "content-creator", "content-humanizer",
    "content-production", "content-strategy", "copywriting", "email-sequence",
    "launch", "launch-strategy", "marketing-psychology", "marketing-strategy-pmm",
    "paid-ads", "programmatic-seo", "schema-markup", "seo-audit",
    "social-content", "social-media-analyzer", "video-content-strategist",
    "x-twitter-growth", "dogfood",
)


def _install() -> None:
    try:
        from agent import coding_context as cc
    except Exception as exc:  # noqa: BLE001 — plugin must never break import
        logger.warning("hc-lean-index: cannot import coding_context: %s", exc)
        return

    if getattr(cc, "_HC_LEAN_INDEX_PATCHED", False):
        return

    # 1. Keep "lean" a distinct mode (upstream aliases it to "focus").
    try:
        aliases = getattr(cc, "_MODE_ALIASES", None)
        if isinstance(aliases, dict):
            aliases["lean"] = "lean"
    except Exception:
        logger.debug("hc-lean-index: could not extend _MODE_ALIASES", exc_info=True)

    # 2. Replace the public resolver the prompt builder imports at call time.
    _orig = getattr(cc, "coding_compact_skill_categories", None)
    if _orig is None:
        logger.warning("hc-lean-index: coding_compact_skill_categories not found")
        return

    def _patched(*, platform=None, cwd=None, config=None):
        try:
            rm = cc.resolve_runtime_mode(platform=platform, cwd=cwd, config=config)
            if getattr(rm, "config_mode", None) == "lean":
                return frozenset(_LEAN_INDEX_CATEGORIES)
        except Exception:
            logger.debug("hc-lean-index: resolve failed — deferring to upstream", exc_info=True)
        return _orig(platform=platform, cwd=cwd, config=config)

    cc.coding_compact_skill_categories = _patched
    cc._HC_LEAN_INDEX_PATCHED = True
    logger.info("hc-lean-index: distinct 'lean' mode installed")


# Install at import as well as at register(): PluginManager calls register(ctx),
# but a fork/embedding that imports the module directly still gets the patch.
_install()


def register(ctx=None) -> None:  # noqa: ARG001 — PluginManager contract
    """Plugin registration entry point (general plugin discovery)."""
    _install()
