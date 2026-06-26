# offline_knowledge.py — Subcommand Architecture & Known Gaps

## Subcommand Pattern

Each knowledge domain (bible, hymns, and any future domain like `lesson`) follows
a 4-layer architecture inside `offline_knowledge.py`:

```
1. CONFIG PATH       — Define directory/file constants at top of script
2. HELPER FUNCTIONS  — Implement search, list, index, stats for the domain
3. ARGPARSE          — Add `subparsers.add_parser("<domain>")` in main()
4. COMMAND DISPATCH  — Add `elif args.command == "<domain>":` handler in main()
```

### Layer 1: Config Paths

Defined near the top of the file (~lines 46-56):

```python
BIBLE_DIR = HOME / "offline" / "bible"
HYMNS_DIR = HOME / "offline" / "hymns"
```

### Layer 2: Helper Functions

Each domain has a pair of helpers — one for listing content, one for searching.
The pattern is:

```python
def <domain>_list_<items>():
    """List available <items> in the domain directory."""
    if not DOMAIN_DIR.exists():
        return {"status": "not_found", "<items>": []}

def <domain>_search(query):
    """Search domain content for the query string."""
    # line-by-line grep through text files, or structured corpus parsing
    # return {"status": "ok", "query": ..., "total_matches": N, "results": [...]}
```

### Layer 3: Argparse Subparser

```python
<domain> = subparsers.add_parser("<domain>", help="...")
<domain>_sub = <domain>.add_subparsers(dest="<domain>_command")
ss = <domain>_sub.add_parser("search", help="...")
ss.add_argument("query", nargs="+", help="...")
<domain>_sub.add_parser("list", help="...")
```

### Layer 4: Command Dispatch

```python
elif args.command == "<domain>":
    if args.<domain>_command == "search":
        ...
    elif args.<domain>_command == "list":
        ...
```

## Known Gap: No `lesson` Subcommand

The `offline_knowledge` tool has `bible` and `hymns` subcommands but NO `lesson`
subcommand. This means:

- `offline_knowledge lesson index` — does not exist
- `offline_knowledge lesson search "error"` — does not exist

### What Would a `lesson` Subcommand Look Like?

The lessons concept uses a different storage model than bible/hymns. Lessons live
as markdown files in `~/brain/<source>/lessons/` directories indexed by gbrain,
not in a flat `~/offline/lessons/` directory.

A `lesson` subcommand would likely:

1. **`lesson index`** — Scan all brain source directories for `lessons/` dirs and
   run `gbrain sync --source <name>` to ensure they're indexed
2. **`lesson search <query>`** — Run `gbrain query <query> --source <source>` (or
   across all sources) targeting `lessons/` content

### Alternative: Use gbrain Directly

Since gbrain already indexes brain directories, searching lessons can be done
without a new subcommand:

```bash
# Search all lessons across all brain sources
gbrain search "error" | grep -i lessons

# Search within a specific source's lessons
gbrain query "error" --source default | grep -i lessons
```

## PATH Issue

`offline_knowledge` is installed at `~/.hermes/bin/offline_knowledge` but
`~/.hermes/bin` is NOT automatically added to PATH. To use the command directly:

```bash
export PATH="$HOME/.hermes/bin:$PATH"
# Add to ~/.zshrc for persistence:
echo 'export PATH="$HOME/.hermes/bin:$PATH"' >> ~/.zshrc
```

Without this, run via full path:

```bash
~/.hermes/bin/offline_knowledge stats
```
