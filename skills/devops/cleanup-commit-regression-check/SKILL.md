---
name: cleanup-commit-regression-check
version: 1.0.0
category: devops
description: When scripts fail with NameError after a mass-edit commit.
platforms: [linux, macos]
---

# Cleanup-Commit Regression Check

## When to Use

Load this when:
- A cron or script fails with `NameError: <name> is not defined` after a
  recent "fix"/"cleanup"/"adversarial findings" commit
- A mass-edit pass (no-op removal, style sweep, linter auto-fix) touched many
  files and you suspect collateral damage
- You need to prove a refactor didn't delete functions

## The Failure Pattern

Mass-edit commits that replace no-op lines (e.g. `_ = None  # expected —
silently handled`) with real handling (e.g. `print(...)`) routinely delete
**structural lines adjacent to the edit** — the very `def` line of the next
function, plus `return` statements. The result compiles (the orphaned body
becomes module-level or attaches to the previous function) but fails at
runtime with NameError or silently misbehaves.

**Confirmed 2026-07-31:** commit `84272894` ("fix: all high adversarial
findings") stripped `def _resolve_var(...)` and `return env` from two bus
scripts, `def embed_skills(...)` + `conn.commit()` + `return count` from a
cache script, `def get_previous_good_sha(...)` + `return None` from a
rollback script, and `def _analyze_python(...)` + `return files` + two
append lines from a project-map script. The bus forwarder cron crashed
every 2 minutes with `NameError: name '_resolve_var' is not defined`.

## Detection — compare function sets, not just syntax

`py_compile` passes on these files (the damage is semantically wrong but
syntactically valid). The reliable check is an **AST function-set diff**
between the commit and its parent:

```python
# For every .py file touched by the suspicious commit:
import ast, subprocess, pathlib

def funcs_of(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

parent = subprocess.run(['git','show',f'{COMMIT}^:{path}'],
                        capture_output=True, text=True).stdout
current = pathlib.Path(path).read_text()
deleted = funcs_of(parent) - funcs_of(current)
if deleted:
    print(f"{path}: DELETED FUNCS: {sorted(deleted)}")
```

Single-function deletions are the smoking gun; wholesale file rewrites
legitimately delete many functions and need manual review instead.

Re-runnable probe: `scripts/find-deleted-funcs.py <commit>` (AST function-set
diff, exit 1 on deletions).

## Companion Trap — Cron Path ≠ Deploy Path

Verifying a cleanup-commit fix surfaced a deeper deployment trap: the cron
runner executes from `~/.hermes/scripts/`, but cortex-update deploys to
`~/.hermes-cortex/scripts/`. The symlink bridge is skipped when local-only
files exist, so deployed fixes silently don't reach the running cron, and
the doctor misses it (it checks the deploy dir, not the cron dir). Full
detail, detection commands, and the safe sync fix:
`references/cron-path-vs-deploy-path.md`.

## Detection — grep for orphaned bodies

A function whose `def` line was stripped leaves its docstring dangling.
Grep for callers of an undefined helper:

```bash
grep -rn "_resolve_var(" ops/scripts/ 2>/dev/null | grep -v "def _resolve_var"
# → files that CALL it without defining it
```

## Fix Pattern

1. `git show COMMIT^:path` — extract the original structural lines
2. Restore exactly: `def <name>(...):` + missing `return` statements +
   any append lines that were collateral
3. Verify with a REAL run, not just `python3 -m py_compile` — execute the
   script or import it so the module-level code exercises the restored
   function
4. Commit, push, deploy via cortex-update.sh
5. Confirm via the cron's output file (`~/.hermes/cron/output/<job>/`)
   that the next tick flips to `silent`

## Pitfalls

- **`py_compile` is NOT verification** for this bug class — orphaned bodies
  compile fine. Run the actual code path.
- **Check ALL files the commit touched**, not just the one that broke.
  The 2026-07-31 case hit 5 files across 4 directories; only the cron
  script surfaced first.
- **Module-level assignments pollute naive AST "undefined name" scans** —
  a plain `used - defined` scan flags every `HOME`, `STATE_DIR`, etc.
  The function-set diff between commit and parent is the precise tool.
- **Deployed copies carry a `# SOURCE:` header** — `diff -q` against the
  repo always reports drift even when synced. Compare deployed vs the
  deploy dir (`~/.hermes-cortex/scripts/`) or strip the header.
