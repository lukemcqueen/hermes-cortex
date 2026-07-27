# Python Import Path Debugging Across CWDs

## Symptom

The same Python script works from one directory but fails from another,
with either `ImportError` or unexpected SKIP/FAIL output. The script
behaves differently depending on the CWD.

## Root Cause

The script's `sys.path` setup adds `os.path.dirname(__file__)` to the
Python import path. Since `__file__` resolves to an absolute path based
on where the script lives on disk — NOT the CWD — this should be CWD-
independent *in theory*. In practice, **the directory structure differs**
between repo and deployed layouts, so the same string pattern resolves
to different directories.

### Concrete example: cortex-doctor.py

| Location | `os.path.dirname(__file__)` | Has `hermes_paths.py`? |
|----------|----------------------------|------------------------|
| Deployed (`~/.hermes-cortex/scripts/`) | `...scripts/` | ✅ yes |
| Repo (`ops/scripts/manage/`) | `...manage/` | ❌ no (it's at `ops/scripts/`) |

From the repo path, `from hermes_paths import ensure_scripts_path` fails
because `hermes_paths.py` is one directory level up. The import guard
catches this and shows SKIP — but for the WRONG reason (not "cortex_bus
not found", but "hermes_paths not found").

## Debugging Steps

### 1. Find what __file__ resolves to

```python
# From the script being debugged:
_this_dir = os.path.dirname(os.path.abspath(__file__))
print(f"__file__ dir: {_this_dir}")
print(f"Parent dir: {os.path.dirname(_this_dir)}")
```

### 2. Check which shared modules are at each level

```python
for level in [_this_dir, os.path.dirname(_this_dir)]:
    has_hp = os.path.exists(os.path.join(level, "hermes_paths.py"))
    has_lib = os.path.exists(os.path.join(level, "lib"))
    print(f"  {level}: hermes_paths={has_hp}, lib/={has_lib}")
```

### 3. Identify the gap

If the import chain is `hermes_paths → ensure_scripts_path → lib.cortex_bus`,
check each link:

1. **Can `hermes_paths` be imported?** Requires `hermes_paths.py` on `sys.path`
2. **Can `ensure_scripts_path()` find the right scripts dir?** Depends on the
   `__file__` resolution of *hermes_paths.py itself* (not the caller)
3. **Can `lib.cortex_bus` be imported?** Requires `lib/` under scripts dir

A failure at step 1 or 2 produces a misleading SKIP — the guard interprets
it as "cortex_bus not available" when really the path setup is incomplete.

## Fix Pattern

In the script that sets up `sys.path` (typically the CLI entry point or
package `__init__`), add the parent directory when it contains shared
modules:

```python
_this_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_dir = os.path.join(_this_dir, "your_package")
if os.path.isdir(_pkg_dir):
    if _this_dir not in sys.path:
        sys.path.insert(0, _this_dir)
    # In-repo case: shared modules live in the parent
    _parent = os.path.dirname(_this_dir)
    _shared_file = os.path.join(_parent, "hermes_paths.py")
    if os.path.exists(_shared_file) and _parent not in sys.path:
        sys.path.insert(0, _parent)
```

This is safe: from the deployed path, the parent doesn't have the shared
module, so nothing extra is added. From the repo, the parent has it, so
the import works.

## Verification

After the fix, test from BOTH paths:

```bash
# Deployed (production) path
python3 ~/.hermes-cortex/scripts/cortex-doctor.py --quiet

# Repo (development) path
cd ~/hermes-cortex && python3 ops/scripts/manage/cortex-doctor.py --quiet
```

Both should produce identical results for the affected test.
