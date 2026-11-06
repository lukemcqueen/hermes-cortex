#!/usr/bin/env python3
"""Cross-platform immutability probe for the doctor + governance auditor.

Linux:  chattr +i / lsattr (e2fs attribute 'i')
macOS:  chflags uchg  (BSD flag 'uchg', visible in `ls -lO`)

2026-09-15: the doctor probed immutability with lsattr alone, which is
absent on macOS — every enforcement file then WARNed/FAILed as
"cannot verify" even though the files WERE protected (chflags uchg
verified by hand on Titus). This module is the single shared probe so
all call sites agree (fix the class, not the ticket).

Helper is parameterized so tests can monkeypatch sys.platform-derived
flags instead of shelling out to real chattr/chflags.
"""

import platform as _platform
import subprocess

_IS_MAC = _platform.system() == "Darwin"


def is_file_immutable(path) -> bool:
  """True if `path` has the immutable flag on THIS OS (Linux lsattr 'i' /
  macOS chflags 'uchg'). False if the flag is absent. Raises OSError /
  subprocess errors if the probe itself fails — the CALLER decides
  whether an unverifiable file should WARN (never silently pass; P12)."""
  p = str(path)
  if _IS_MAC:
    r = subprocess.run(
        ["ls", "-lO", p], capture_output=True, text=True, timeout=5
    )
    if r.returncode != 0:
      raise OSError(f"ls -lO exit {r.returncode}")
    return "uchg" in r.stdout.split()
  r = subprocess.run(
      ["lsattr", p], capture_output=True, text=True, timeout=5
  )
  if r.returncode != 0:
    raise OSError(f"lsattr exit {r.returncode}")
  flags = r.stdout.split()[0] if r.stdout else ""
  return "i" in flags


def immutable_remediation(path) -> str:
  """OS-correct remediation string for a file missing the immutable flag."""
  if _IS_MAC:
    return f"chflags uchg {path}   (or: sudo hermes-plugin-lock lock)"
  return f"sudo chattr +i {path}   (or: sudo hermes-plugin-lock lock)"
