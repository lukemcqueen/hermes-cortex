# gbrain npm Package Collision

## The Problem

The npm registry contains **two different packages** with the name `gbrain`:

### 1. stormcolor/gbrain (WRONG PACKAGE)
- **npm:** `gbrain@1.3.1`
- **Publisher:** stormcolor
- **Published:** 2018 (dead project)
- **Description:** "GPU Javascript"
- **GitHub:** No active repository
- **CLI:** NO binary exposed (no `bin` entry in package.json)
- **Status:** Abandoned, not the knowledge base tool

**What happens when you install it:**
```bash
bun install -g gbrain
# or
npm install -g gbrain
```

The package installs successfully but:
- `which gbrain` returns empty
- No CLI binary is created
- `gbrain --version` fails with "command not found"
- The installed code is a webpack-bundled GPU JS library (Draggabilly, Packery, etc.)

### 2. garrytan/gbrain (CORRECT PACKAGE)
- **npm:** NOT PUBLISHED (install from GitHub only)
- **GitHub:** `github.com/garrytan/gbrain`
- **Stars:** 20.9k
- **Description:** Postgres-native personal knowledge base
- **Features:**
  - Hybrid RAG search (vector + keyword)
  - Self-wiring knowledge graphs
  - Synthesis and gap analysis
  - PGLite local storage
  - Multi-source sync
- **CLI:** Full CLI with `gbrain` command
- **Install:** `bun install -g github:garrytan/gbrain`

## Detection

If you've installed the wrong package:

```bash
# Check what's installed
bun pm ls -g | grep gbrain

# Check for binary
which gbrain  # Returns empty if wrong package

# Inspect package.json
cat /usr/local/lib/node_modules/gbrain/package.json
# Look for: "name": "gbrain", "version": "1.3.1", "author": "stormcolor"
# Missing: "bin" entry
```

## Resolution

```bash
# Remove wrong package
bun remove -g gbrain
npm uninstall -g gbrain  # If installed via npm

# Install correct package
bun install -g github:garrytan/gbrain

# Verify
gbrain --version  # Should return "gbrain 0.42.25.0" or similar
which gbrain      # Should return ~/.bun/bin/gbrain
```

## Why This Happens

1. **npm namespace squatting:** The stormcolor package claimed the `gbrain` name in 2018
2. **No conflict resolution:** npm/bun don't warn about name collisions with dead packages
3. **GitHub naming:** The real gbrain uses GitHub URL installation, bypassing npm entirely

## Prevention

**Always use the GitHub URL:**
```bash
bun install -g github:garrytan/gbrain
```

**Never use:**
```bash
bun install -g gbrain      # WRONG - gets stormcolor package
npm install -g gbrain      # WRONG - gets stormcolor package
```

## Impact on hermes-cortex

The `install.sh` script was patched (commit 376a00f) to use the correct installation command:

```bash
# Before (broken)
bun install -g gbrain

# After (fixed)
bun install -g github:garrytan/gbrain
```

If you encounter the wrong package during installation:
1. Remove it completely
2. Install from GitHub
3. Run `gbrain init --pglite` to initialize
4. Continue with the rest of the install script

## Related Issues

- gbrain requires source directories to be git-initialized
- The `default` gbrain source is built-in and cannot have `--path` configured
- Use `--source mybrain` instead of `--all` for sync operations
