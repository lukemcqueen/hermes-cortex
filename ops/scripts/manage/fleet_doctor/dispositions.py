"""Doctor warning/info DISPOSITIONS — a deferred warning must be a RECORDED decision.

Operator, 2026-10-20: "I'm getting tired of seeing agents just gloss over the warnings after a
cortex update. Can we encourage the agents to fix warnings and info too? I don't want mandatory,
however, I don't want them to just ignore it every time."

Why guidance alone had not worked: the doctor's own REQUIRED ACTIONS block ended every remedy with
"recovery is its OWN governed change, not part of the update cycle", so deferral was not merely
permitted — it was SUGGESTED — and it was free: no record, no owner, no expiry. The summary printed
counts only, so a warning somebody had decided about looked exactly like one nobody had ever read,
which made "the warnings are pre-existing" unfalsifiable from the output.

This module makes the deferral legitimate but RECORDED, and nothing more. No check becomes a FAIL,
no gate reads this store, and the doctor's exit codes are unchanged. What changes is that an
undisposed warning is now VISIBLE as undisposed, and disposing of one is a single command.

Store: ``<CORTEX_HOME>/state/doctor-dispositions.json``

    {check_name: {"disposition": "deferred"|"deliberate"|"fixed",
                  "owner": "<agent or operator>", "reason": "<why>",
                  "recorded_at": "<iso8601>"}}

Keyed by the check NAME, never the detail text: details carry counts that move constantly, and a
disposition that invalidates itself on every count change is re-litigated daily and ignored within
a week.

EXPIRY: a disposition older than ``DOCTOR_DISPOSITION_TTL_DAYS`` is STALE and counts as undisposed
again. Deferral is renewed, never eternal — an eternal disposition is the same silence with extra
steps.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from .config import CORTEX_HOME

STORE_PATH = CORTEX_HOME / "state" / "doctor-dispositions.json"

# How long a decision stands before it has to be renewed. A malformed override must not stop the
# doctor from starting: fall back to the default and say so.
try:
    TTL_DAYS = int(os.environ.get("DOCTOR_DISPOSITION_TTL_DAYS") or "30")
except ValueError:
    TTL_DAYS = 30

DISPOSITIONS = ("fixed", "deferred", "deliberate")

# The statuses this mechanism governs. A FAIL is not a disposition candidate — it must be fixed,
# and the footer already says so.
GOVERNED_STATUSES = ("WARN", "INFO")


class DispositionError(Exception):
    """A record that must NOT be written (invalid, or the store is not writable)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load(path=None) -> dict:
    """Every recorded disposition. FAIL-SOFT: an unreadable store yields {}.

    Soft is correct HERE because this is the READ path of a tool that runs on every host, inside
    gates, including hosts whose state dir is read-only. An unreadable store makes every warning
    undisposed, which is the visible direction — never a silent pass. (The explicit WRITE path is
    the opposite: see `record`.)
    """
    try:
        raw = (path or STORE_PATH).read_text()
    except (FileNotFoundError, OSError):
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def state_for(name: str, store: dict | None = None, now: datetime | None = None) -> str:
    """``"disposed"``, ``"stale"`` or ``"undisposed"`` for one check name."""
    entry = (store if store is not None else load()).get(name)
    if not isinstance(entry, dict):
        return "undisposed"
    stamp = str(entry.get("recorded_at") or "")
    if not stamp:
        return "stale"                      # a decision with no date cannot be aged, so it is not
    try:
        recorded = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return "stale"
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    if (now or _now()) - recorded > timedelta(days=TTL_DAYS):
        return "stale"
    return "disposed"


def describe(name: str, store: dict | None = None, now: datetime | None = None) -> str:
    """A one-line label for a disposed check, e.g. ``deferred (esther, since 2026-10-20)``."""
    entry = (store if store is not None else load()).get(name) or {}
    what = str(entry.get("disposition") or "?")
    owner = str(entry.get("owner") or "?")
    since = str(entry.get("recorded_at") or "")[:10] or "?"
    tag = state_for(name, store, now)
    return f"{what} ({owner}, since {since})" + (" — STALE, renew it" if tag == "stale" else "")


def undisposed(checks, store: dict | None = None, now: datetime | None = None) -> list:
    """The checks an agent still has to decide about: WARN/INFO with no live disposition.

    ``now`` is the testability seam for the expiry rule: a 30-day clock is not something a test
    can wait on, and a rule that can only be exercised by waiting is a rule that gets asserted
    from the source instead of measured.
    """
    store = store if store is not None else load()
    out = []
    for c in checks or []:
        if str(c.get("status")) not in GOVERNED_STATUSES:
            continue
        if state_for(str(c.get("name") or ""), store, now) == "disposed":
            continue
        out.append(c)
    return out


def record(name: str, disposition: str, owner: str, reason: str, path=None,
           checks=None) -> dict:
    """Write ONE decision, or raise ``DispositionError``.

    Deliberately NOT soft: an explicit `--disposition` write that failed silently would exit
    successfully without recording anything, which is the exact failure this module exists to
    prevent (review finding ADV-0-2). Every refusal below is a real one:

      * a disposition outside the vocabulary, or an empty owner/reason — a decision with no name on
        it is not a decision;
      * a check name that is not in the CURRENT run — a typo must not create a phantom disposition
        for a check that does not exist;
      * ``fixed`` while the check is still WARN/INFO/FAIL — that claim would be false, and "fixed"
        must not become a way to hide a live warning (review finding ADV-0-3).
    """
    if disposition not in DISPOSITIONS:
        raise DispositionError(
            f"--as must be one of {'|'.join(DISPOSITIONS)}, got {disposition!r}")
    if not str(owner).strip():
        raise DispositionError("--owner is required: a decision with no name on it is not a decision")
    if not str(reason).strip():
        raise DispositionError("--reason is required: record WHY it is being deferred or kept")

    if checks is not None:
        current = {str(c.get("name")): str(c.get("status")) for c in checks}
        if name not in current:
            raise DispositionError(
                f"no check named {name!r} in this run — refusing to record a disposition for a "
                f"check that does not exist")
        status = current[name]
        if disposition == "fixed" and status in ("WARN", "INFO", "FAIL"):
            raise DispositionError(
                f"check {name!r} is currently {status}: 'fixed' would be a false claim. Fix it and "
                f"re-run, or record it as deferred/deliberate with the reason.")

    store = load(path)
    store[name] = {"disposition": disposition, "owner": str(owner).strip(),
                   "reason": str(reason).strip(),
                   "recorded_at": _now().isoformat().replace("+00:00", "Z")}
    target = path or STORE_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n")
    except OSError as e:
        raise DispositionError(f"could not write {target}: {e}") from e
    return store[name]
