# Skills distribution and enumeration

Deep dive for the always-on rule "expose a skills tree to many harnesses — enumerate the READER
first". Read this when wiring skills into a harness, moving where skills live, or when one harness
"does not see" the skills another one does.

## Where harnesses look (know this before inventing a path)

The Agent Skills spec defines what is INSIDE a skill (a directory holding `SKILL.md` with `name` +
`description` frontmatter) — never where the folder lives. That is why every tool also has a private
path, and why a cross-client convention emerged alongside them:

| Path | Read natively by |
|---|---|
| `.agents/skills/` (project), `~/.agents/skills/` (user) | the cross-client convention: Codex, Cursor, Copilot CLI, OpenCode, Antigravity |
| `~/.claude/skills/`, `.claude/skills/` (private) | Claude Code |
| `~/.codex/skills/`, `~/.cursor/skills/`, `~/.pi/agent/…` | tool-private; Pi additionally takes an explicit path list in its settings |
| `~/.hermes/skills/` | the Hermes agent (this fleet's legacy path) |

Consequences that shape a design:

- **Put the tree at the standard path and most harnesses need NO wiring.** Reserve pointers for the
  private-only readers.
- **Declare a harness's capability from its OWN output**, not from a doc: an entry claiming
  `discovery` for a harness that can only read an instruction file is a false capability. Where the
  mechanism is an instruction pointer, say `instructions`.
- Skill directories may be NESTED (`<category>/<name>/SKILL.md`); the skill's identity is the folder
  holding `SKILL.md`, not the category above it.

## Progressive disclosure costs what it exposes

Tier 1 is the catalog: every installed skill's name + description is pre-loaded at session start
(≈50-100 tokens per skill), the body is read only when the skill is activated, and supporting files
only when the body points at them. So "expose all N skills" costs roughly `N × 100` tokens on EVERY
session of every harness that reads that tree. Some harnesses cap the catalog themselves (shortening
descriptions first, or omitting skills past a budget), which turns a large catalog into a silently
partial one — measure the count a harness actually reports before assuming it saw everything.

Decide the catalog size deliberately. Two legitimate shapes:

- **Register all of them** — simplest, and the cost is paid whether or not a skill is used.
- **Register one generated index** (the names + one-line triggers) and open bodies by path — same
  reachability, one description in the catalog, cost paid on use.

Whichever you pick, the LIST should be derived from a generated inventory rather than hand-kept, so
it cannot drift from the tree it describes.

## The exposure mechanism is the READER's property — measured

Same content, three mechanisms, four readers. Counts are `SKILL.md` files visible from the root:

| Mechanism | pathlib `rglob` | `os.walk` | `os.walk(followlinks=True)` | plain `find` |
|---|---|---|---|---|
| Root itself is a symlink → real tree | sees it | sees it | sees it | **0 — does not traverse** |
| Real root containing a per-skill symlink | **0** | **0** | sees it | **0** |
| Real copy | sees it | sees it | sees it | sees it |

Read the table as three rules, not a preference:

1. **A per-skill symlink FARM is invisible to a plain scan.** It works only where the consumer
   already registers each entry itself (a harness with an explicit path list). Never adopt it as the
   general exposure mechanism — the failure is silent: the directory looks full and the scan reports
   nothing.
2. **A symlinked ROOT is visible to path-opening readers** (the walk resolves its starting
   directory) but not to `find` without `-L`. A reader that enumerates with a `find`-default walk
   sees NOTHING through a pointer, while one that opens the directory sees everything. This is the
   single most useful thing to establish about a harness before wiring it.
3. **A real copy is visible to every reader** — that is the escape hatch for a harness proven not to
   follow, at the price of a second copy that must be verified against the owner.

### Probe recipe (run it, do not reason about it)

Build a throwaway tree with one `SKILL.md` under `real/<cat>/<name>/`, then create each candidate at
a temp path and count from the root the way the harness would:

```python
import os, pathlib, shutil
root_link = tmp / "as-link"; os.symlink(real, root_link)               # root is a pointer
root_farm = tmp / "as-farm"; os.symlink(real / "cat", root_farm / "cat")  # per-skill pointer
root_copy = tmp / "as-copy"; shutil.copytree(real, root_copy, symlinks=True)

len(list(root.rglob("SKILL.md")))          # pathlib
sum(f == "SKILL.md" for _d, _dn, fn in os.walk(root) for f in fn)   # os.walk
```

Then confirm against the shell form the harness may use: `find <root> -name SKILL.md` versus
`find -L <root> -name SKILL.md`, and record the numbers in the artifact. **Do not generalise from a
passing probe on ONE reader** — the whole point is that the mechanisms differ per reader, so the
probe belongs beside the harness's declared capability.

## Ownership: one real tree, everything else derived

- The tree that is REAL is the owner. Every other path is a pointer or a DERIVED mirror.
- A DERIVED mirror is verified against the owner (a content comparison, or a coverage check that
  every owned skill is readable at the mirror) — never hand-edited, never an independent owner.
- Move, never copy-then-delete, when relocating a real tree: rename the tree into place, then create
  the pointer, then VERIFY (owner is a real directory; the pointer resolves to it; the skill count
  is unchanged from the pre-move count). Refuse to guess when BOTH paths are real directories — that
  is two owners, and the resolution needs an explicit operator decision with the non-winning tree
  preserved by rename, never deleted.
- **A pointer inherits the writer's habits.** Nothing guarantees a foreign writer opens a pointer
  path rather than replacing the directory entry. Prove it by writing through the pointer path and
  asserting the file landed in the owner tree; keep a check that the direction cannot silently
  revert, and make the installer/updater run that check so an un-inverted host self-heals instead of
  reporting a clean update.
- Direct paths still resolve through a pointer even where a WALK does not — so "a file read through
  the pointer works" is not evidence that the harness can enumerate the tree.
