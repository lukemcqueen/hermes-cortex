# What the gate counts as a WRITE, and what to do when no repo resolves

Two behaviours that read as "the gate is broken" but are the gate working. Both measured on a
macOS host on 2026-10-18 (a session reported "blocking all bash calls because CORTEX_SESSION_REPO
isn't set and we're not in a git repo").

## 1. `cd` is NOT a read primitive — a cd-chain is a BLOCKED write

`cd /repo && git status` is treated as WRITE-class. `cd` is not a read primitive, so the compound
loses its lock-free status and is refused when no lock is held. The command is obviously harmless,
which is exactly why the refusal reads as nonsense.

Inspect lock-free by passing the directory on the CALL rather than in the command:

    terminal(command="git status --short", workdir="/repo")     # lock-free
    terminal(command="cd /repo && git status --short")            # WRITE-class, blocked

One read primitive with an absolute path is equally fine. Never build a cd-chain to orient yourself.

## 2. A session with NO repo is unblocked, not locked out

The gate resolves the governed repo from path-like tool arguments, then from the repo the SESSION
already resolved (recorded by `_note_session_repo` from an earlier call's own arguments).

**It never reads `CORTEX_SESSION_REPO`.** That variable plays no part in resolution, so "export
CORTEX_SESSION_REPO" is not the fix for a locked-out session, whatever the error suggests.

When neither source yields a repo the refusal is its own message, not the generic lock rule: it says
governance is repo-scoped so no lock could authorise the call, names the escapes that work
(`workdir=<repo>`, a path inside the checkout, or `begin_change` from the repo), and states that
read-only commands never need a lock.

Recovery from a locked-out session, all of it always permitted:

    terminal(command="ls ~")
    terminal(command="find ~ -maxdepth 3 -name <repo-name> -type d")
    # then pass workdir=<that path> on the write-class call, and begin_change() from there

The failure this replaced: the old refusal told an agent to acquire a lock it could not mint, while
the compound it needed to FIND the checkout was itself write-class — a closed loop with no exit.
