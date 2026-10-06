# Evidence — un-break `hermes update` (upstream tree + pm dependency build)

Date: 2026-10-06 · Host: esther · Repo commit: `dc51b3a0` (on `origin/main`)

## 1. Root cause, corrected against live evidence

The stated cause ("the updater refuses to pull into a dirty tree") is **false for
git installs**: the git updater **auto-stashes** local changes, pulls, then
restores them. The update receipt recorded a successful stash+restore step while
still advancing the checkout.

The real blocker was the **dependency build**: the pm-managed CPython 3.14 is
built with `CC=clang` / `CXX=clang++`, but these hosts ship `gcc`/`g++` only.
The `matrix` extra's `python-olm` has no cp314 wheel, so pm builds it from
source and dies with `No such file or directory: 'clang++'`, failing the whole
update at dependency-sync. Fix: export `CC=gcc` / `CXX=g++` in the update wrapper.

## 2. Re-executable verification

```bash
git -C ~/.hermes/hermes-agent status --porcelain          # -> empty (clean)
CC=gcc CXX=g++ hermes update -y --no-gateway-restart       # -> completes green
python3 ops/scripts/manage/cortex-doctor.py --quiet
```

## 3. Captured command output (this session)

`git -C ~/.hermes/hermes-agent status --porcelain` -> empty, before and after
`cortex-update.sh`.

`python3 ops/scripts/manage/cortex-doctor.py --quiet` (doctor):

```
  PASS  Deploy sync
  PASS  Hermes tree clean
  WARNING  Overall:  (440 pass, 4 warn, 0 fail, 7 info)
```
