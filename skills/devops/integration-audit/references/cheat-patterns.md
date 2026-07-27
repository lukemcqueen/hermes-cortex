# Cheat Detection Regex Reference

Known cheat patterns and their regex signatures for adversarial verification.
Covers the patterns detected by `adversarial-verify.py --level A2`.

## Error Swallowing (most common)

Code catches an exception and does nothing.

### Multi-line form
```python
try:
    dangerous_op()
except:
    pass
```
**Regex:** `except\s*(?:\w+\s*)*:[^\S\n]*\n\s*(?:pass|#|#.*|'''|""")\s*(?:\n|$)`

### Single-line form
```python
except: pass
```
**Regex:** `except\s*(?:\w+\s*)*:\s*pass\s*(?:#|$)`

## Regex Pitfall: `\s*` eats newlines

❌ **Wrong:** `except: \s*\n\s*pass`  — `\s*` between `:` and `\n` greedily matches the newline, so `\n` can never match.

✅ **Fixed:** `except: [^\S\n]*\n\s*pass` — `[^\S\n]*` matches whitespace WITHOUT newlines, leaving `\n` to match.

## Type Suppression
Pattern: `# type: ignore` or `@ts-ignore`
Regex: `type:\s*ignore|@ts-ignore`

## Global Lint Suppression
Pattern: `# flake8: noqa` or `# pylint: disable=all`
Regex: `noqa|pylint:\s*disable`

## No-Op Fix Detection
Check if only test files were changed (no source change):
```bash
git diff --name-only HEAD | grep -v "^tests/" | grep -v "^test_"
# If empty, only tests changed — possible no-op
```

## Assertion Count Drop
```bash
git diff HEAD -- tests/ | grep "^+" | grep -c "assert\|expect\|should"
git diff HEAD -- tests/ | grep "^-" | grep -c "assert\|expect\|should"
# If dropped > added, assertions were stripped
```
