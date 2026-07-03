# gbrain Source Migration: PGLite Export Script

The script below exports all pages from a gbrain PGLite database to markdown
files at nested directory paths, writing the correct `slug:` into frontmatter
for accurate reimport. Used during the June 2026 source merge (default →
mybrain).

## Schema Notes

The gbrain `pages` table stores content in `compiled_truth`, NOT `content`:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'pages'
ORDER BY ordinal_position;
```

Key columns:
- `slug` (text) — slug with underscores, e.g. `sources_docs_testing`
- `compiled_truth` (text) — rendered markdown, possibly wrapped in `<>` + HTML-escaped
- `frontmatter` (jsonb) — YAML frontmatter as JSON
- `source_id` (text) — which source the page belongs to
- `title` (text) — page title
- `page_kind` (text) — page type classification
- `updated_at` (timestamptz) — last update time

## Export Script

```typescript
const path = require("path");
const fs = require("fs");
const { PGlite } = require(
  path.join(process.env.HOME,
    ".bun/install/global/node_modules/@electric-sql/pglite/dist/index.cjs")
);

const TARGET = path.join(process.env.HOME, "brain", "default");

async function main() {
  const db = await PGlite.create(
    "file://" + path.join(process.env.HOME, ".gbrain", "brain.pglite")
  );
  const r = await db.query(
    "SELECT slug, coalesce(compiled_truth,'') as content FROM public.pages ORDER BY slug"
  );
  console.log(`Found ${r.rows.length} pages`);

  let written = 0;
  for (const row of r.rows) {
    const dbSlug = row.slug;  // e.g. "sources_docs_testing"
    let content = row.content || "";

    // gbrain wraps in angle brackets
    if (content.startsWith("<") && content.endsWith(">"))
      content = content.slice(1, -1);

    // Convert DB slug (underscore-separated) to filesystem path (slash-separated)
    // e.g. "sources_docs_testing" → "sources/docs/testing"
    const fsSlug = dbSlug.replace(/_/g, "/");

    // Ensure slug in frontmatter (gbrain sync uses this during import)
    if (!/^---\s*\nslug:/.test(content)) {
      if (content.startsWith("---\n"))
        content = content.replace("---\n", `---\nslug: ${fsSlug}\n`);
      else
        content = `---\nslug: ${fsSlug}\n---\n${content}`;
    }

    const targetPath = path.join(TARGET, fsSlug + ".md");
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.writeFileSync(targetPath, content, "utf-8");
    written++;
  }

  await db.close();
  console.log(`Written ${written} files to ${TARGET}`);
}
main().catch(e => console.error("FAIL:", e.message.slice(0, 500)));
```

## Key Details

- **Slug conversion**: gbrain stores slugs flat with underscores (`sources_docs_testing`). The script converts to slashes for filesystem nesting (`sources/docs/testing.md`).
- **Frontmatter injection**: Without `slug:` in frontmatter, gbrain's `sync` generates the slug from the file path. Explicit `slug:` ensures the reimport produces the exact same slug as before.
- **Angle bracket wrapper**: gbrain wraps `compiled_truth` in `<>` when the page has a frontmatter-based title. Strip them before writing.
- **Collision guard**: When a slug IS a directory prefix for another page (e.g. `sources/docs/architecture` is both a page and a parent of `sources/docs/architecture/research`), both files coexist — gbrain handles nested paths correctly via frontmatter slugs.

## Verification After Export

```bash
# Count files matches expected page count
find ~/brain/default -type f -name "*.md" | wc -l

# Verify frontmatter slugs are correct
head -3 ~/brain/default/sources/docs/testing.md
# Expected: "---\nslug: sources/docs/testing\n---"

# Check for file-vs-directory collisions
find ~/brain/default -type f -name "*.md" | while read f; do
  dir="${f%.md}"
  [ -d "$dir" ] && echo "COLLISION: $f"
done
```
