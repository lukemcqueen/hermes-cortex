# Evidence Recipes — making a claim checkable

Q2 of the skill says every claim needs real tool output. These are the SHAPES that satisfy it when the
obvious route is unavailable or too weak. Each is: when to use it, the shape, and why the weaker
version is not enough.

## 1. Substance-read a value out of the shipped artifact

**When:** the suite that would pin a value cannot run in this environment, or a default was just
changed and you must show the change actually landed.

**Shape:** parse the file and assert the literal, then print what you extracted so the run itself is
the evidence:

```python
src = pathlib.Path("path/to/module.py").read_text()
vals = {}
for node in ast.walk(ast.parse(src)):
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id == "THE_CONSTANT":
            vals["THE_CONSTANT"] = ast.literal_eval(node.value)
print("value =", vals["THE_CONSTANT"])
assert vals["THE_CONSTANT"] == expected
```

**Why:** quoting a line proves the text contains a string; extracting the value proves what the code will
execute. Label the result a SUBSTANCE check, never a suite pass.

## 2. Verify the ACTIVE artifact, not the tree you edited

**When:** the change only matters once it runs — a deployed module, an installed console script, a
config the daemon reads.

**Shape:** grep the copy the runtime actually loads for the changed line, and show the path in the
output so the reader can tell WHICH copy was checked.

**Why:** repo and deployed copies diverge between the edit and the deploy. A green check on the
stand-in copy is a false green — the same trap as demonstrating a stale binary.

## 3. Assert the exception TYPE and its message

**When:** a guard's contract is to RAISE on bad input rather than return a value.

**Shape:** capture broadly into a variable, then assert the type and a message fragment:

```python
err = None
try:
    subject()
except BaseException as exc:      # broad ON PURPOSE: an unexpected type must surface, not be swallowed
    err = exc
assert isinstance(err, ExpectedError), f"got {type(err).__name__}: {err}"
assert "expected fragment" in str(err)
```

**Why:** a narrow `except` passes while the wrong thing raised. And do not assume a test framework's
`raises()` helper exists in a file that must also run standalone — write the assertion, not the import.

## 4. Assert IDENTITY, not a count

**When:** the property under test is that the SAME unit was handled twice (a retry, a re-send, an
idempotent replay).

**Shape:** have the collaborator record what it received; assert `seen[0] == seen[1] == expected`.

**Why:** `len(seen) == 2` is also satisfied by two DIFFERENT units, which is the bug a retry test exists
to catch.

## 5. Pin a deliberate value as a contract, and sweep what stated the old one

**When:** you change a default or any other value someone could silently re-tune.

**Shape:** a test asserting the constant equals the new value, the reason in the docstring — and in the
SAME change, every doc, comment or template that STATED the old value.

**Why:** a default is a contract. Material written before the flip becomes a false statement the moment
it lands, and the passage you wrote earlier in the same session is the most likely offender because you
remember writing it correctly.

## 6. Poison the collaborators a unit must NOT touch

**When:** a unit's contract is that it does not consult the store, the network, or a sibling lookup.

**Shape:** replace those with stubs that raise, and restore EVERY attribute you patched in a `finally`.

**Why:** it proves non-use, and it removes any dependence on another test having cleaned up after
itself — a test that relies on a sibling's teardown fails unpredictably when the order changes.
