# Shell Script Testing Patterns

## Testing Bash Scripts with Node.js (`.cjs`)

When bash scripts need real integration tests (not just shellcheck), Node.js
with `child_process` provides a reliable test harness:

```javascript
// restore-backup.test.cjs — must use .cjs for CommonJS child_process
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

// Use execSync for script execution — captures exit code
// Use try/catch + JSON.parse to validate structured output
// Use temp dirs (os.tmpdir()) for isolation
```

**Why `.cjs`?** Node.js `child_process` requires CommonJS (`require`). ESM modules
with `import` can cause issues in the same file.

**Key patterns:**
- `execSync(cmd, { cwd: workDir, encoding: 'utf8' })` — run script, capture output
- Throws on non-zero exit — wrap in try/catch for negative tests
- `JSON.parse(stdout)` — validate audit logs, manifest files
- Temp dir per test with `fs.mkdtempSync` + cleanup in `afterEach`

## Cross-Platform Hash Computation

Linux has `md5sum`, macOS has `md5`. Neither works on both.

```bash
# macOS-compatible hash (falls back to "unavailable" if neither present)
if command -v md5 > /dev/null 2>&1; then
  HASH=$(md5 -q "$file")
elif command -v md5sum > /dev/null 2>&1; then
  HASH=$(md5sum "$file" | cut -d' ' -f1)
else
  HASH="unavailable"
fi
```

The `md5 -q` flag on macOS outputs just the hash, no filename. `md5sum` on Linux
outputs `hash  filename` — use `cut -d' ' -f1` to isolate the hash.

**Never assume `md5sum` exists.** It's Linux-only. macOS users will get `command not found`.

## Reserved Keyword Collision in JS Test Code

The bash variable name `exports` collides with JavaScript's reserved keyword
`exports` (used by CommonJS `module.exports`). If the bash script sets
`exports=...` and the Node.js test reads it back with `JSON.parse()`, the
resulting JS object will have a property literally named `exports` that
collides with the CommonJS scope.

**Fix:** Rename the bash variable to `BACKUP_FILES` or similar non-reserved name.

## Script Placement Convention

Operational scripts belong in `scripts/migration/`, not embedded in documentation
or `_local_docs/`. Separation of concerns:

- `_local_docs/` — runbooks, story files, design docs
- `scripts/migration/` — executable scripts that operators run

This keeps docs readable while making scripts discoverable and version-controllable.

## Relative Path Assumption

Migration scripts often use relative paths (`./exports/`, `./converted/`). This
is intentional — scripts are designed to run from the migration workspace root.
Document this clearly: "Run from the migration workspace directory."

Absolute paths to the script itself work regardless of cwd:
```bash
~/Developer/ACME/acme-royalty/scripts/migration/restore-backup.sh
# ...but the script's own relative paths resolve from cwd, not from script location
```