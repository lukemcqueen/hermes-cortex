#!/usr/bin/env python3
"""
cortex_lib/tools.py — Hermes-independent file-tool surface (canonical).

Provides the small read_file/write_file surface that fleet scripts used to pull
from the Hermes runtime's `hermes_tools`, implemented in the stdlib so the
module resolves with ZERO Hermes import (component-hermes-separation S1b).

The interface mirrors the Hermes tool shapes the migrated callers already use:
  read_file(path=...)  -> {"content": <str>, ...}   (dict, "content" key)
  write_file(path=..., content=...)                 (creates parent dirs)

This is a *thin stdlib adapter*, deliberately: it is NOT a re-implementation of
Hermes' toolchain (search/web are Hermes-core, not vendored here). Only the
file-I/O surface is replicated so the one migrated caller (analyze-failures.py)
runs standalone. New Hermes-core tool consumers should keep using Hermes tools
in-session; this module exists to remove the runtime import from the fleet
scripts that never actually needed the agent loop.
"""
from __future__ import annotations

import os
from pathlib import Path


def read_file(path: str | os.PathLike[str], **kwargs) -> dict:
    """Read a text file and return a dict with a ``content`` key.

    Mirrors the Hermes ``read_file`` return shape the migrated callers index
    (```content["content"]```); extra kwargs are accepted and ignored for
    call-compatibility. Raises OSError on missing/unreadable file — no
    silent empty.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    return {"content": text, "path": str(p)}


def write_file(path: str | os.PathLike[str], content: str, **kwargs) -> dict:
    """Write ``content`` to ``path``, creating parent dirs.

    Returns a dict (``{"verified": True}``) mirroring the Hermes tool's
    reporting shape. Atomic-ish: writes then the caller may re-read to verify.
    """
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"verified": True, "path": str(p)}