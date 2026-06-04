# [Feature Name] Implementation Plan

**Goal:** One sentence describing what this builds

**Architecture:** 2–3 sentences about approach, key files, and data flow

---

### Task 1: [Short Action Name]

**Time estimate:** 2–5 min / one `change-test-loop` cycle

**Files:**
- Create: `path/to/new/file.py`
- Modify: `path/to/existing.py:42` (line-number hint)

**Step 1 — Write failing test**

```python
def test_specific_behavior():
    # Arrange
    # Act
    # Assert
    pass
```

**Step 2 — Verify RED**

```bash
pytest path/to/test_file.py::test_specific_behavior -v
```
Expected: FAIL — reason

**Step 3 — Write minimal code**

```python
# Minimal implementation
```

**Step 4 — Verify GREEN**

```bash
pytest path/to/test_file.py::test_specific_behavior -v
```
Expected: PASS

**Step 5 — Run full suite for regressions**

```bash
pytest tests/ -x -q
```
Expected: all pass

**Step 6 — Commit**

```bash
git add path/to/new/file.py path/to/test_file.py
git commit -m "<type>: <short description>"
```

---

### Task 2: [Short Action Name]

**Files:**
- Modify: `path/to/file.py:15-30`
- Update: `path/to/config.py:42`

**Step 1 — Write failing test**

```python
def test_next_behavior():
    pass
```

**Step 2 — Verify RED**

```bash
pytest path/to/test_file.py::test_next_behavior -v
```
Expected: FAIL

**Step 3 — Write minimal code**

```python

```

**Step 4 — Verify GREEN**

```bash
pytest path/to/test_file.py::test_next_behavior -v
```
Expected: PASS

**Step 5 — Run full suite** — Expected: all pass

**Step 6 — Commit**

---

> Add more tasks as needed. Every task must start with a failing test.
> If the first slice cannot be done in one loop, it is too big.
