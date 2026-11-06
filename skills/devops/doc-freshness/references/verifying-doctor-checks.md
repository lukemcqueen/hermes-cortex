# Verifying a doctor check (hermetic RED/GREEN, no live files touched)

For a new or changed check in `cortex_doctor/checks.py`, prove both branches
against a temp tree, never by editing live host files (a ~/.claude/CLAUDE.md
edit to test RED also trips the deployed doctor mid-test).

## Recipe

1. **Import as a PACKAGE — standalone `exec_module` fails.** checks.py uses
   package-relative imports (`from .immutability import ...`), so a bare
   `importlib.util.spec_from_file_location` + `exec_module` raises
   "attempted relative import with no known parent package". Put the doctor
   package's dir on `sys.path` and `import cortex_doctor.checks`.
2. **Repoint the module's GLOBALS, not the files.** Checks read `HOME` /
   `CORTEX_REPO` at call time. Build a temp tree, plant the harness files
   there, then assign `chkmod.HOME = tmp` and `chkmod.CORTEX_REPO =
   tmp / "repo"`. No live path touched.
3. **Fake the Results object.** A check only calls
   `res.add(label, severity, detail, fix=None)`; a class whose `add` appends
   to a list is a faithful harness for asserting which branch fired.
4. **RED**: plant the condition the check exists to flag (e.g. a retired
   canonical token) in the temp tree → assert the FAIL/WARN branch fires and
   names the file. **GREEN**: clean the temp files → assert PASS. Both
   directions, or the new branch is untested.
5. **Run with the fleet venv** (`~/.steadfaste-fleet/venv/bin/python3`) — it
   has the doctor's deps (yaml, mcp); a bare `python3` may lack them and the
   import fails for the wrong reason.
6. **After deploy, run the REAL doctor and grep for the check's name** — the
   doctor executes from the DEPLOYED tree, so the deployed copy must carry the
   check before a green run proves anything about the runtime path.

## Pitfall while writing the check itself

A filter expression that calls a helper whose return you also need leaves the
tuple variable UNBOUND:

```python
# NameError at runtime: w is never bound
hits = [(p.name, w) for p in files if p.exists() and _conflicts(p)]
# bind with the walrus in the filter
hits = [(p.name, w) for p in files if p.exists() and (w := _conflicts(p))]
```

Lint catches it at write time — fix before running, not after the probe fails
naming the wrong line.
