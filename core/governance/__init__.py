"""
Core Governance — Loop governance engine.

This package is the canonical location for the loop-governance engine.
The legacy location at src/loop-governance/ is a backward-compat shim.

Modules (all expected to be run as scripts or imported individually):
    loop_db         — SQLite-backed governance database
    loop_scorer     — LLM-as-Judge trace quality scoring
    loop_feedback   — User feedback (accept/override) ingestion
    score_cycle     — CLI entry point for scoring cycles
    loop_config     — Threshold and weight configuration
    loop_evaluator  — Cycle evaluation and model comparison
    auto_apply      — Auto-apply scoring fixes
    session_cache   — Session embedding cache
    inbox_watcher   — Watch inbox for governance-related messages
    skill_miner     — Extract skill lessons from past cycles
"""
