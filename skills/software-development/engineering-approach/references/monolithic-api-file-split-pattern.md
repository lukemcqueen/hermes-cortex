# Monolithic API Client File Split

How to split a large, monolithic frontend API client file (1328+ lines) into domain-specific modules.

## When to Use

The frontend `lib/api.ts` or equivalent has grown to 1000+ lines with every API function in one file. The file has clear domain sections delimited by comment headers (`// ── Works ──`). Hooks/components import individual functions by name from the barrel.

## Step 1 — Analyze the file

Use the terminal to split by section headers:

```bash
python3 -c "
import re
with open('src/lib/api.ts') as f:
    content = f.read()
sections = re.split(r'\n(?=// ──)', content)
for i, s in enumerate(sections):
    first = s.strip().split('\n')[0][:90]
    print(f'S{i}: {first} ({len(s)} chars)')
"
```

This reveals the domain groupings and their sizes. Merge small related sections (e.g., Publisher Portal + Publisher Dashboard + Member Portal → `portal.ts`).

## Step 2 — Write the split script

Create a Python script (`/tmp/split_api.py`) that:
1. Reads the original file
2. Splits by section header delimiter
3. Writes each section to its own file under `lib/api/<name>.ts`, prefixing with a shared helper import: `import { fetchJSON, API_BASE } from "./index";`

Merge sections for grouped files (admin.ts, portal.ts) by concatenating their bodies.

## Step 3 — Create the barrel `index.ts`

The barrel re-exports everything:

```typescript
import type { /* shared types from api-types.ts */ } from "../api-types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "...";

function getToken(): string | null { ... }

export async function fetchJSON<T>(...) { ... }

export const api = { get, post, patch, delete };

// Re-export all domain modules
export * from "./auth";
export * from "./works";
// ... etc
```

**Backward compatibility:** Keep the original `api.ts` as a one-line re-export:
```typescript
export * from "./api/index";
```
This lets existing `import { fn } from '@/lib/api'` still resolve.

## Step 4 — Fix type imports

Each domain file references types from `api-types.ts`. Detect needed types:

```python
# For each domain file, find types referenced but not imported
type_pattern = re.compile(r'^export (?:type |interface |class )(\w+)', re.MULTILINE)
all_types = set(type_pattern.findall(api_types_content))
used_types = [t for t in all_types if re.search(r'\b' + re.escape(t) + r'\b', content)]
```

Add `import type { TypeA, TypeB } from "../api-types";` to each file.

**Types defined inline** (like `CwrImportListItem`, `ImportFieldDefinition`) stay in their domain file — they're not in api-types.ts.

## Step 5 — Update consumer imports

Search for `from.*lib/api` across the entire `src/` to find consumers:

- **Hooks** (`src/hooks/*.ts`): May already import from specific sub-modules. Update any that still import from the old barrel path.
- **Page-level files** (`src/app/[locale]/*/use-*.ts`): Import portal functions from `@/lib/api/portal`.
- **Component files**: Check for direct `@/lib/api` imports.

## Step 6 — Update test mocks

Test files mock `@/lib/api` with `vi.mock('@/lib/api', ...)`. After splitting, hooks import from sub-module paths. Update:

1. Change `vi.mock('@/lib/api', ...)` to `vi.mock('@/lib/api/<submodule>', ...)`
2. Change `import * as api from '@/lib/api'` to `import * as api from '@/lib/api/<submodule>'`
3. The mock factory must return the same shape as the submodule's actual exports

For `use` hooks that dynamically import on test: update the dynamic import path too.

**Pitfall:** Some test files may have been pre-updated by a previous subagent iteration. Always check the current content before editing.

## Verification

1. `npx tsc --noEmit` — must pass (or have same pre-existing errors as before)
2. `npx vitest run` — test count should match (same pass/fail ratio as pre-split)
3. All import paths in the original api.ts must be covered by the barrel re-exports

### Critical: check for conflicting barrel exports

After creating domain modules, **scan for duplicate named exports** across all modules that are star-exported from the barrel. Two modules exporting `createSociety` via `export *` causes a hard build error:

```
The requested module './societies' contains conflicting star exports for the names
'createSociety', 'listSocieties' with the previous requested module './admin'
```

**Detection script (run after every split):**

```python
import re
from collections import defaultdict

all_exports = {}
for mod in ['auth', 'works', 'creators', 'contracts', 'members', 'publishers',
            'shares', 'admin', 'societies', 'portal', ...]:  # all barrel modules
    with open(f'src/lib/api/{mod}.ts') as f:
        exports = re.findall(r'^export (?:function|const|let|var|interface|type|enum) (\w+)', f.read(), re.MULTILINE)
        all_exports[mod] = set(exports)

# Find names that appear in multiple modules
export_to_modules = defaultdict(list)
for mod, exports in all_exports.items():
    for exp in exports:
        export_to_modules[exp].append(mod)

for name, mods in sorted(export_to_modules.items()):
    if len(mods) > 1:
        print(f'CONFLICT: {name} exported from {", ".join(mods)}')
```

**Fixes:**
- **Same function, different endpoint** (e.g. `/admin/societies` vs `/societies`): rename one version with a prefix (`adminCreateSociety`, `adminListSocieties`), update all consumers and hooks.
- **Accidental duplicate** (same function in two files): remove one, update imports.
- **Move shared utility functions** to a separate module that doesn't conflict.

## Parallel delegation strategy

For this task, use `delegate_task` with a detailed context block (file sections, module map, test files to update). The subagent needs:
- `terminal` + `file` toolsets
- The original file content analysis
- A complete mapping of which function goes to which module
- The list of test files that need mock path updates
