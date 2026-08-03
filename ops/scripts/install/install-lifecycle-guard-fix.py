#!/usr/bin/env python3
"""
install-lifecycle-guard-fix.py — Patch Hermes Agent's gateway-lifecycle guard.

Fixes a false positive in ~/.hermes/hermes-agent/cron/lifecycle_guard.py:
`_iter_command_segments` split multi-line commands on newlines BEFORE
tokenizing, so a `python3 -c "..."` payload with embedded newlines had its
interior lines parsed as standalone shell segments. A path literal inside
the payload (e.g. sqlite3.connect('/home/.../loop-governance.db')) then
looked like a referenced shell script; reading it (33MB > 1MB scan cap)
failed closed and the whole command was blocked with a bogus
"cannot restart or stop the gateway" error.

The fix makes the tokenizer quote-aware across lines — a quoted string
spanning newlines is ONE argument, exactly what the shell itself does.
The direct gateway-lifecycle regex is unchanged, so literal
`hermes gateway restart` / `systemctl restart hermes-gateway` /
`launchctl` / `pkill` commands remain blocked (incl. inside payloads).

Re-run after every ``hermes update`` to re-apply the patch (Hermes
replaces its own source directory on update).

Usage:
    python3 install-lifecycle-guard-fix.py            # apply if missing
    python3 install-lifecycle-guard-fix.py --force    # re-apply always
    python3 install-lifecycle-guard-fix.py --status   # check state
    python3 install-lifecycle-guard-fix.py --uninstall
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.expanduser("~/.hermes/hermes-agent/cron/lifecycle_guard.py")

# ── The old (buggy) tokenizer — exact text from the deployed file ──
OLD = '''def _iter_command_segments(command: str) -> Iterator[list[str]]:
    """Yield shell-tokenized command segments, honoring quotes and comments."""
    normalized = command.replace("\\\\\\n", "")
    for line in normalized.splitlines() or [normalized]:
        try:
            lexer = shlex.shlex(
                line,
                posix=True,
                punctuation_chars=";&|()",
            )
            lexer.whitespace_split = True
            lexer.commenters = "#"
            tokens = list(lexer)
        except ValueError:
            continue

        segment: list[str] = []
        for token in tokens:
            if token and set(token) <= _CONTROL_CHARS:
                if segment:
                    yield segment
                    segment = []
                continue
            segment.append(token)
        if segment:
            yield segment
'''

# ── The fixed tokenizer — quote-aware across lines ──────────────
NEW = '''def _iter_command_segments(command: str) -> Iterator[list[str]]:
    """Yield shell-tokenized command segments, honoring quotes and comments.

    Quote-aware across lines: a quoted string spanning newlines (e.g. a
    multi-line ``python3 -c "..."`` payload) is ONE argument, mirroring
    what the shell itself does. Splitting on newlines first made interior
    payload lines look like standalone commands, and a path literal inside
    the payload was misread as a referenced shell script — blocking
    innocent commands (e.g. ``python3 -c`` querying a >1MB sqlite DB)
    with a bogus gateway-lifecycle error.
    """
    normalized = command.replace("\\\\\\n", "")
    lines = normalized.splitlines() or [normalized]
    buffer = ""
    for line in lines:
        buffer = f"{buffer}\\n{line}" if buffer else line
        try:
            lexer = shlex.shlex(
                buffer,
                posix=True,
                punctuation_chars=";&|()",
            )
            lexer.whitespace_split = True
            lexer.commenters = "#"
            tokens = list(lexer)
        except ValueError:
            # Unclosed quote — join the next line and re-tokenize
            continue
        buffer = ""

        segment: list[str] = []
        for token in tokens:
            if token and set(token) <= _CONTROL_CHARS:
                if segment:
                    yield segment
                    segment = []
                continue
            segment.append(token)
        if segment:
            yield segment

    # Trailing unclosed quote (EOF): nothing more to join — drop, as the
    # original did (the direct regex still scans the raw command text).
    if buffer:
        try:
            lexer = shlex.shlex(
                buffer,
                posix=True,
                punctuation_chars=";&|()",
            )
            lexer.whitespace_split = True
            lexer.commenters = "#"
            tokens = list(lexer)
        except ValueError:
            return
        segment: list[str] = []
        for token in tokens:
            if token and set(token) <= _CONTROL_CHARS:
                if segment:
                    yield segment
                    segment = []
                continue
            segment.append(token)
        if segment:
            yield segment
'''

MARKER = "Quote-aware across lines"  # present only in the fixed version


def _apply(force=False):
    if not os.path.exists(GUARD):
        print(f"  FAIL lifecycle_guard.py not found at {GUARD}")
        return False
    with open(GUARD) as f:
        content = f.read()

    if MARKER in content:
        print("  SKIP already applied (use --force to re-apply)")
        return True
    if OLD not in content:
        print("  FAIL old tokenizer text not found — upstream may have changed it")
        return False
    count = content.count(OLD)
    if count > 1:
        print(f"  FAIL old text appears {count} times, can't uniquely patch")
        return False

    content = content.replace(OLD, NEW, 1)
    with open(GUARD, "w") as f:
        f.write(content)
    print(f"  OK   patched {GUARD}")
    return True


def _status():
    print("=== Gateway-lifecycle guard fix status ===")
    if not os.path.exists(GUARD):
        print(f"  MISS lifecycle_guard.py not found at {GUARD}")
        return
    with open(GUARD) as f:
        content = f.read()
    if MARKER in content:
        print("  OK   quote-aware tokenizer applied")
    else:
        print("  MISS quote-aware tokenizer NOT applied (run install without --force)")


def _uninstall():
    if not os.path.exists(GUARD):
        print(f"  FAIL lifecycle_guard.py not found at {GUARD}")
        return
    with open(GUARD) as f:
        content = f.read()
    if MARKER not in content:
        print("  SKIP not applied")
        return
    if NEW not in content:
        print("  FAIL can't find patch text to revert")
        return
    content = content.replace(NEW, OLD, 1)
    with open(GUARD, "w") as f:
        f.write(content)
    print("  OK   reverted to original tokenizer")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--uninstall" in args:
        _uninstall()
    elif "--status" in args:
        _status()
    else:
        ok = _apply(force="--force" in args)
        sys.exit(0 if ok else 1)
