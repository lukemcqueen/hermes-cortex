# Package Rename with a One-Release Compat Shim

Use when renaming a python package (directory + import surface) that runtime components import
— MCP servers, scripts, hooks, tests, parent-walk bootstraps. The shim keeps non-redeployed
and legacy callers resolving during the transition window instead of forcing a simultaneous
fleet-wide deploy.

## The shim (mechanism)

The OLD directory keeps ONLY shim files:

- `old_pkg/__init__.py` — import the new package and each submodule, then alias:
  `import new_pkg` … `sys.modules[__name__] = new_pkg` and per submodule
  `sys.modules[f"{__name__}.{sub}"] = getattr(new_pkg, sub)`. `import old_pkg` then hands back
  the NEW module object; add the submodule aliases only after importing them so they exist as
  attributes at all times.
- A PHYSICAL re-exporter for any file a parent-walk bootstrap probes, e.g.
  `old_pkg/paths.py` with `from new_pkg.paths import <names>` (explicit names, not `*`). A
  non-redeployed consumer's `(scripts_dir / "old_pkg" / "paths.py").is_file()` check never
  imports — without the physical file the walk finds nothing and its caller never adds
  scripts/ to sys.path, and the failure is silent until an import from a bare path.

The package and the shim deploy as a pair ONLY when a DEPLOYED artifact imports the old
name (a deployed entrypoint, an MCP server on the deployed tree). A package the live gateway
runs from the REPO tree needs its shim in the repo but deliberately NOT registered — deploying
a shim nothing on the deployed tree reads is noise, and leaving its `register` line out keeps
the map honest. Judge "is it a pair" per package by grepping what the deployed tree imports,
never by reflex. The map's EXACT count then changes (one register entry per real file, plus the
shim IF it deploys), so re-sync the deploy-registry doc AND its count-asserting test in the
same commit; a count test that parses a literal deployed-shape total goes RED otherwise.

## A live daemon that loads a renamed module goes genuinely stale — restart AFTER the deploy

A rename edits modules a running daemon/MCP server loads BY PATH. A content-first doctor check
(sha-stamp compared against the file) then fires a real stale-daemon warning the moment the
token edit bumps the file's mtime. Restarting right after the repo edit is premature: the
daemon loads the DEPLOYED copy, which the deploy updates — so restart once, after
`cortex-update.sh`, not twice. Identify which copy the daemon loads (its argv `.py` path)
before restarting, and restart again if a later deploy rewrites that copy. A stale-daemon
warning cleared only by killing the process is a genuinely-stale daemon, not silenceable —
clear it for real by restarting, not by editing output.

## Verify by IDENTITY, not importability

`old_pkg is new_pkg`, `old_pkg.sub is new_pkg.sub`, `old_pkg.paths.f is new_pkg.paths.f` — the
same callable, not a copy. That identity is the whole point of the transition, so pin it with
committed tests and run them from BOTH the repo tree and the DEPLOYED tree (`sys.path`
prepended with `<deploy>/scripts`). A shim that merely re-defines functions at import time
passes importability checks while silently breaking `is`-based consumers.

## Transform traps

- Use the word-boundary guard `(?<![A-Za-z0-9_])old_pkg(?![A-Za-z0-9_])`. The guard
  deliberately does NOT match compound identifiers — `old_pkg_dir`-style locals survive the
  pass, then stay as inconsistencies. They are the residual grep's job: grep `old_pkg` without
  the boundary after the pass and hand-fix every compound hit.
- The transform rewrites the moved package's own DOCSTRINGS: a line "renamed from `old_pkg`"
  becomes "renamed from `new_pkg`" INSIDE new_pkg — a self-contradiction the close reviewer
  reads and always files. Exclude the self-documentary files (the shim, the moved package's
  own docstrings, the plan/evidence that quotes the history) from the transform, then audit the
  moved package's docstrings anyway.
- Stale deployed copies of the old SUBMODULES linger after the first redeploy. The shim's
  sys.modules aliasing means they are never imported, but they mislead later readers and any
  tree-scan. Purge the deployed copies of every old submodule except the shim files right after
  deploying.

## Batch pollution: tests read the DEPLOYED tree

A re-export shim on the deployed tree references a new package that has not been deployed yet,
so identity assertions fail in the BATCH while the same file passes alone. Signature: the
failing module's path sits under the deployed scripts dir (e.g. `~/.steadfaste-fleet/scripts/`)
while the repo copy is correct. Deploy FIRST, then re-run the batch; the deployed copy is the
runtime truth any identity test ultimately triggers.

## Close-review scoping of moved test files

The close reviewer judges changed or renamed TEST files against the cycle's task description
and flags assertions on subjects OUTSIDE the range as fabrication — a renamed test file that
drags in pre-existing coverage (the old package's register-map test, a sibling package's
hermetic invariant) reads as over-claim. Three moves keep the cycle clean:

1. Move out-of-slice tests out of the renamed file (with their own slice; re-add them when
   that slice lands) instead of keeping unrelated green tests in the range.
2. Rename test functions whose NAMES contradict their bodies — a name saying `reexports_old`
   while the body asserts the new package is a defect the reviewer quotes verbatim.
3. ADD tests pinning the cycle's actual subject — the shim identity — so the reviewer has
   something to check the range against rather than only the drifted leftovers.

## Deploy-order gates

The push gate runs a deployed-tree checksum; any post-deploy edit to a renamed/shared file
yields a "Checksum: <file>" FAIL. Re-deploy in a small empty cycle (begin → deploy → accept →
end, no file edits) before pushing, and treat the checksum FAIL as the reminder, not an error.

## Dry-run triage, full-deploy exit criterion

A deploy script's `--dry-run` STILL runs the doctor at the end. Two consequences:

- **A non-zero dry-run rc is a REAL signal.** The doctor tail means a crash loop, a stale
  unit, or any other `❌` check fails the dry-run too — and it is usually a genuine defect the
  rename exposed (a live unit on purged paths, a checksum the dry-run caused). Grep the dry-run
  output for `❌` lines and triage each named check before re-attempting.
- **The dry-run lists mapped files as "would copy" — it copies nothing.** The doctor's
  `Checksum: <file>` FAIL for your own fresh edit to the deploy script is therefore EXPECTED
  on a dry-run and clears only on a real deploy. The exit criterion for the rename is the
  FULL deploy rc=0 (and a verified deployed-file mode), never the dry-run.

## Live systemd units execute the purge — repair AND rename them

Repo transforms and the deployed-tree library purge cannot touch host-local per-instance
units (`~/.config/systemd/user/*.service` written by an install flow, e.g. a per-bot gateway
unit). They keep ExecStart on the renamed package's PURGED path; the moment the deploy lands
they enter a systemd auto-restart loop (`activating auto-restart`, NRestarts climbing) that
fails the doctor's "Systemd crash loops" check and every deploy after it. Sweep them
DELIBERATELY: `grep -Rl '<old_pkg>' ~/.config/systemd/user/` and list unit files for the old
family name. When one is found, fix BOTH halves — the paths AND the unit name: `systemctl
--user stop` + `disable` the old unit, `mv` the file to `fleet-…-<instance>.service`, update
its Description, `daemon-reload`, then `enable --now` and verify `ActiveState=active` with no
`activating` entries. Patching only the ExecStart and restarting under the old name leaves
the old NAME as the stale artifact — the operator will send it back ("stop it to fix the
name").

## A rewritten script loses its +x bit, and the deploy will not restore it

A rename procedure that regenerates a script or shim through a text writer drops its mode to
644. The deploy's change detector is content-only (checksums) — an identical-content file is
never re-copied, so the mode sticks at 644 on the deployed tree while the repo shows 755
(visible only as a doctor FAIL or a mode check). Fix in the SAME commit: `chmod +x` the repo
file AND add a `MODE_OVERRIDES` entry keyed to the deployed path in the deploy script's
per-file loop (which runs unconditionally after copy), then verify the deployed mode 
(`stat -c '%A'`) after the real deploy.

## Rewrite the review material after EVERY fix round

The material is the close reviewer's ONLY window into the change. Re-reviewing with the
pre-fix material after fixes landed re-flags the exact claims the fixes corrected — when the
fresh evidence contradicts the material's old prose, the reviewer files it as
FABRICATION rather than as a stale document. Before each `--re-review`: drop superseded
claims, cite the committed artifacts by path (the evidence file, the new test file, the
committed counts), and state counts unambiguously as "N failed / M passed" (a bare "4/15"
reads as 4 failures and draws a fabrication finding for the misstatement).

## The blob close-loop grinds at ~4 blobs/pass — delegate the grind

A rename commit that touches hundreds of files (a name token appears in most of them) leaves
hundreds of changed blobs for the end-change close loop, judged a few per pass with the
judging time dominated by LLM latency on docs. The loop is content-keyed and strictly
monotonic (each pass's "CLEAN in the range" only grows, never re-judges), so a BACKGROUND
subagent that just keeps calling `end_change` with the same task_id until the close message
arrives can grind the whole queue while the owner session does read-only survey work. Give
the child the expectation up front that "⏳ Cannot close yet: N blob(s)" is the NORMAL
intermediate answer, a cap (e.g. 120 calls), and the DB query to confirm the final status.
