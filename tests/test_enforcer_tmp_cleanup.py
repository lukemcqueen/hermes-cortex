"""Hermetic tests for the lock-free /tmp-cleanup carve-out.

Covers the sanctioned scratch-cleanup shape and the escape/abuse shapes that
must STILL be lock-gated. Drives the module directly (no live store).

Operator: /tmp cleanup must not demand a repo lock a finished task no longer
holds (Titus's `rm -f /tmp/...` after all cycles closed was gated).
"""
import importlib.util
import os
import pathlib
import sys

import pytest

_ENFORCER = "plugins/governance-enforcer/__init__.py"


def _load():
    repo = pathlib.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "enf_tmp_test_mod", repo / _ENFORCER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


MOD = _load()


def _ok(cmd):
    return MOD._is_sanctioned_tmp_cleanup_command(cmd) is True


def _no(cmd):
    return MOD._is_sanctioned_tmp_cleanup_command(cmd) is False


# ── Sanctioned (lock-free) ──────────────────────────────────────────────────

SANCTIONED = [
    "rm -f /tmp/adv-review.py /tmp/plan_8241.md && rm -rf /tmp/templates && echo cleaned",
    "rm -f /tmp/x && echo done",
    "rm -rf /tmp/thing && echo cleaned",
    "rm -f /tmp/a /tmp/b /tmp/c",
    "rmdir /tmp/emptydir && echo cleaned",
    "/bin/rm -f /tmp/x",
    "/usr/bin/rm -rf /tmp/sub/dir && echo cleaned",
    "rm /tmp/x",
]


@pytest.mark.parametrize("cmd", SANCTIONED, ids=[f"s{i}" for i in range(len(SANCTIONED))])
def test_tmp_cleanup_is_sanctioned(cmd):
    assert _ok(cmd)


# ── Blocked (still needs a lock / refused) ─────────────────────────────────

BLOCKED = [
    "rm -rf /tmp",                       # bare scratch root itself
    "rm -rf /home/esther/x",             # outside scratch
    "rm /tmp/../repo/x",                 # .. escape
    "rm -rf /tmp/x*",                    # wildcard
    "rm -rf /tmp/x?",                    # wildcard
    "sudo rm /tmp/x",                    # sudo
    "rm /tmp/x; echo hi",                # semicolon
    "rm /tmp/x | cat",                   # pipe
    "rm /tmp/x > /tmp/log",              # redirect
    "cd /tmp && rm x",                   # cd
    "mv /tmp/x /tmp/y",                  # mv
    "rm ~/x",                            # home
    "rm -rf /tmp/one && rm /home/two",   # one bad operand poisons the chain
    "rm /tmp/a && echo",                 # echo with no arg
    "rm -rf /tmp/one && sudo rm /tmp/two",
    "echo cleaned && rm /tmp/x",         # banner must be LAST
    "rm -- -rf /tmp/x",                  # -- poison
    "python3 -c 'import shutil; shutil.rmtree(\"/tmp/x\")'",  # not rm at all
    "rm -f $HOME/../x",
    "",
    "/usr/local/bin/rm -f /tmp/x",       # unexpected path prefix
]


@pytest.mark.parametrize("cmd", BLOCKED, ids=[f"b{i}" for i in range(len(BLOCKED))])
def test_tmp_cleanup_unsafe_is_blocked(cmd):
    assert _no(cmd)


# ── $TMPDIR resolution ──────────────────────────────────────────────────────

def test_tmpdir_var_operand_resolves():
    """A $TMPDIR operand ALWAYS resolves against /tmp, never TMPDIR's own value."""
    os.environ["TMPDIR"] = "/tmp"
    assert _ok("rm -f $TMPDIR/scratch.txt && echo done")
    # A $TMPDIR that points outside /tmp is NOT promoted to a scratch root:
    # the operand resolves to /home/esther/scratch.txt and is refused.
    os.environ["TMPDIR"] = "/home/esther"
    assert _no("rm -f $TMPDIR/scratch.txt")
    # Nor may $TMPDIR be used to reach home even if it contains the /tmp shell.
    del os.environ["TMPDIR"]


# ── resolved-path escape ────────────────────────────────────────────────────

def test_double_slash_and_dot_escape_blocked():
    """realpath resolution defeats /tmp//.. and .. escapes."""
    assert _no("rm -rf /tmp//../repo/x")
    assert _no("rm -rf /tmp/../repo/x")
    assert _no("rm -rf /tmp/foo/../../repo/x")
    assert _no("rm -rf /tmp/a/../b")   # . still resolves inside, but .. refused