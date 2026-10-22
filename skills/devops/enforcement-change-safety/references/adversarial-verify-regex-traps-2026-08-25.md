# Adversarial-Verify Regex Traps When Editing Gated Files (2026-08-25)

`adversarial-verify.py` uses line-anchored regexes that false-positive on STYLE,
not real bugs. Both were hit zeroing findings on `loop-gov-mcp.py` (A4 gate).

## Trap 1: Empty-except regex flags comments, not just `pass`

The A2/A4 pattern:

```python
empty_excepts = re.findall(
    r"except\b[^\n:]*:\s*(?:\n[ \t]*)?(?:pass|#.*)(?:\n|$)", content,
)
inline_swallows = re.findall(
    r"except\b[^\n:]*:\s*(?:pass|_ = None)\s*(?:#|$)", content,
)
```

Matches an except whose first body line is a comment, OR whose colon is
followed by an inline comment. Both of these are flagged as empty excepts even
though a real statement follows:

```python
# FLAGGED — comment is the first body line
except (json.JSONDecodeError, OSError, ValueError):
    # P1-A: unparseable = possibly mid-write
    log.warning("Skipping unparseable lock file: %s", name)

# FLAGGED — inline comment after the colon
except Exception as err:  # noqa: BLE001 — degrade, never crash
    fallback()
```

**Fix:** put a REAL statement (`log.warning(...)`) FIRST in every except body;
comments go AFTER the statement. Do not put an inline comment after the colon.

```python
# CLEAN
except (json.JSONDecodeError, OSError, ValueError) as err:
    log.warning("Skipping unparseable lock file: %s (%s)", name, err)
    # P1-A: unparseable = possibly mid-write. Leave it — never delete.

# CLEAN
except Exception as err:
    fallback()
    # degrade, never crash
```

## Trap 2: subprocess-no-timeout is per-line

The check iterates line-by-line; `timeout` must appear ON THE SAME LINE as the
`subprocess.check_output(`/`run(` call. A `timeout=3` on the next argument
line is invisible to it → false "no timeout" finding:

```python
# FLAGGED — timeout on a different line than the call
repo_root = subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"],
    stderr=subprocess.DEVNULL, timeout=3,
).decode().strip()

# CLEAN — timeout on the call's first argument line
repo_root = subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], timeout=3, stderr=subprocess.DEVNULL,
).decode().strip()
```

## Verification

Verify edits with the same regex the gate uses:

```bash
python3 -c "
import re
content = open('<file>.py').read()
pat1 = re.compile(r'except\b[^\n:]*:\s*(?:\n[ \t]*)?(?:pass|#.*)(?:\n|\$)', re.M)
print('PAT1 lines:', [content[:m.start()].count(chr(10))+1 for m in pat1.finditer(content)])
pat2 = re.compile(r'except\b[^\n:]*:\s*(?:pass|_ = None)\s*(?:#|\$)', re.M)
print('PAT2 lines:', [content[:m.start()].count(chr(10))+1 for m in pat2.finditer(content)])
"
```

Or simply run the A4 gate and confirm 0 findings before commit — the deployed
gate is the judge: `python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <file> --level A4 --gate`.

Note: the verifier's `--json` output may mix stale/cached findings from prior
runs (it reported findings against `core/governance/loop_evaluator.py` while
scanning `loop-gov-mcp.py`) — trust the terminal gate output, not the JSON
finding list, for what blocks a commit.
