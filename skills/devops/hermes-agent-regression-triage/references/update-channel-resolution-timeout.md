# `hermes update` dies at channel resolution — probe recipe

Use when `hermes update` aborts with
`Could not resolve the <channel> source channel: Command '['git', 'merge-base',
'--is-ancestor', '<a>', '<b>']' timed out after 10 seconds. No update was applied.`

`<b>` is HEAD. `<a>` is the release commit the channel resolves to.

## Call sites

- `hermes_cli/update_cmd_check.py` — `resolve_source_target(...)` inside
  `retrying_reads()`; a `SubprocessError` (TimeoutExpired is one) prints the
  error and exits 1.
- `hermes_cli/source_releases.py` — `_head_containing()` runs
  `merge-base --is-ancestor <release> HEAD` via a `run()` helper that passes
  `timeout=10`.
- `hermes_cli/source_check.py` — `source_git_env()` sets `GIT_NO_LAZY_FETCH=1`
  (from `NO_LAZY_FETCH_ENV` in `hermes_cli/_subprocess_compat.py`) and
  `GIT_OPTIONAL_LOCKS=0`.
- `hermes_cli/update_cmd.py` — the target-ref fetch happens only AFTER channel
  resolution, so it cannot rescue the probe.

## Step 1 — is it the probe, or the repo?

```bash
cd ~/.hermes/hermes-agent
time git merge-base --is-ancestor <release-sha> HEAD; echo "rc=$?"
```

Present → ~0.2s / rc=1. Absent → ~50s of CPU, then
`fatal: Not a valid commit name` (rc=128). The 10s cap is what turns that into
an abort.

## Step 2 — rule out I/O and pack layout (do this, do not assume)

The walk needs only COMMITS, and it is not I/O bound:

```bash
# evict the packs from page cache, then re-time (non-destructive: cache only)
python3 - <<'PY'
import ctypes, glob, os
libc = ctypes.CDLL("libc.so.6", use_errno=True)
for p in glob.glob(os.path.expanduser("~/.hermes/hermes-agent/.git/objects/pack/*")):
    fd = os.open(p, os.O_RDONLY)
    libc.posix_fadvise(fd, 0, 0, 4)   # POSIX_FADV_DONTNEED
    os.close(fd)
PY
```

Measured on an affected host: warm 0.23s, cold 0.32s, with
`/usr/bin/time -v` reporting `File system inputs: 0` on the warm run — so cold
cache, 34 packs, a missing commit-graph and a missing MIDX are all NOT the cause.

```bash
# the walk needs no fetch: commits are all present
git rev-list --missing=print HEAD | grep -c '^?'            # 0
# missing BLOBS are expected and irrelevant for a commit-only walk
git rev-list --objects --missing=print HEAD | grep -c '^?'  # large number
```

## Step 3 — confirm the object is absent, and where it lives upstream

```bash
git config --get remote.origin.promisor              # true
git config --get remote.origin.partialclonefilter    # blob:none
git config --get-all remote.origin.fetch             # only +refs/heads/main:...
git tag --contains <release-sha>                     # EMPTY = not local
git branch -a --contains <release-sha>               # EMPTY = not local

git ls-remote origin | grep <release-sha>
# refs/tags/vX.Y.Z^{} and refs/heads/release/X.Y.Z — tag/branch only, never main
```

The commit is only reachable from a tag or release branch, and the clone's
refspec fetches neither, so it could only ever arrive by lazy fetch.

## Step 4 — prove the mechanism on a throwaway sha

Any sha that is not in the object store reproduces it without touching real
objects:

```bash
time timeout 120 env GIT_NO_LAZY_FETCH=1 git merge-base --is-ancestor \
    1111111111111111111111111111111111111111 HEAD
# warning: lazy fetching disabled; some objects may not be available
# fatal: Not a valid commit name ...
# real ~50s, user ~50s  <- CPU-bound, and the guard did NOT prevent it
```

`GIT_TRACE=1` stops emitting after the lazy-fetch warning while the CPU burns —
no further syscalls, so it is not a network wait. Disabling the promisor for the
one command (`git -c remote.origin.promisor=false ...`) does not change it.

## Step 5 — fix and verify

```bash
git config --add remote.origin.fetch '+refs/tags/v*:refs/tags/v*'
git fetch --no-tags origin 'refs/tags/v*:refs/tags/v*'

git tag --contains <release-sha>        # now lists the release tag
time git merge-base --is-ancestor <release-sha> HEAD          # ~0.2s
time env GIT_NO_LAZY_FETCH=1 GIT_OPTIONAL_LOCKS=0 \
    git merge-base --is-ancestor <release-sha> HEAD          # ~0.2s
hermes update --check                                        # rc=0
```

Note `git rev-parse vX.Y.Z` returns the TAG object sha for an annotated tag; use
`git rev-parse vX.Y.Z^{}` (or `git tag --contains`) to confirm the COMMIT is local.

## Residual

A later release commit is again absent when the probe runs, because nothing on the
probe path fetches. Options: a `git fetch --tags` before updating, or a pre-fetch
wired into the update path. The upstream defect is the ordering plus the 10s cap;
do not patch the checkout to work around it.
