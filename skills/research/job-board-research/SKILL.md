---
name: job-board-research
version: 1.0.0
category: research
description: "Use when compiling vetted job listings from job boards."
platforms: [linux]
---

# Job-Board Research — Compiling Vetted Job Lists

Workflow for requests like "find AI jobs in Korea with no Korean requirement":
aggregate listings from multiple boards, verify each posting against the
actual JD, and deliver a filtered, linked report.

## Procedure

### 1. Source board inventory

Run searches to find curated boards before scraping generic ones:
- Curated English-JD boards (e.g. Seoulstart `/jobs/english-jobs`, Dev Korea) — highest signal for language-friendly filters.
- LinkedIn guest search — biggest volume; paginates via `&start=N` (25/page, stops serving beyond ~100).
- Company career pages only when the aggregator mirrors them; direct pages (Coupang) may be Cloudflare-walled — use the aggregator instead of fighting the WAF.

### 2. Scrape the data layer, not the rendered page

- Check raw HTML for `<script type="application/ld+json">` with `"@type":"ItemList"` — most job boards embed full item data (title, org, location, apply URL, description). Parse with a regex anchored on the ItemList script; sites carry several LD+JSON blocks and a broad `<script>` match grabs the wrong one.
- Paginate via URL parameter with `requests` + 0.3–0.5s sleep; only fall back to browser DOM scraping when data is client-rendered.
- LinkedIn guest job pages: description lives in `div.show-more-less-html__markup`; plain requests fetch works without login.
- Run browser sessions with `session=` name to keep them isolated.

### 3. Throttle — the user has an explicit standing rule

The user said "Don't get banned". This is a hard gate on bulk fetching:
- 2.5–5s jittered delay between requests; never a tight loop.
- On 429: stop after 3, back off 60s, and stop entirely if the pattern repeats. Do not retry-hammer.
- Batch fetches into groups of ~35 with a save-to-disk checkpoint between batches so a timeout doesn't lose progress.

### 4. Verify requirements against full JDs

Title-based filtering lies. A posting titled in English can still require
Korean (or the reverse). For each posting:

1. Fetch the full JD (LinkedIn guest page, Greenhouse/Ashby direct, board detail page).
2. Classify: `no_requirement` / `korean_required` / `unknown` (source not fetchable) using BOTH:
   - Regex on requirement phrases: `fluent/native/business-level Korean`, `bilingual fluency in Korean and English`, `Korean communication`, `TOPIK`, plus the local-language equivalents (e.g. `한국어 능통`, `한국어로 원활`).
   - Script-ratio check: Hangul chars / (Hangul + ASCII letters) > ~35% means the JD itself is in the local language — treat as risky, list separately.
3. A single-pass regex misses bilingual phrasing like "English and Korean" under required qualifications. Run the soft scan (any mention of the language at all) over the pass set and read each hit's context before finalizing.

### 5. Deliver a tiered report

Write a markdown file with:
- **Tier 1 — fully verified**: language-clean JDs, direct apply links, grouped by company.
- **Risky tier** — local-language JDs with no explicit fluency requirement; label "confirm with recruiter".
- **Excluded** — what was removed and the evidence phrase that removed it, so the filter is auditable.
- Deliver via `MEDIA:` path in chat.

## Pitfalls

- Don't classify from titles alone — half of English-titled postings carry a local-language requirement buried in the qualifications section.
- Parse JSON-LD with a targeted regex; a broad script match returns the site's Organization/WebSite schema and yields zero jobs while looking successful.
- Non-LinkedIn sources (Ashby, Greenhouse, company boards) are usually fetchable via plain requests even when an aggregator is walled — check them individually instead of marking the whole posting unverified.
- Count exclusions as well as inclusions: the user trusts the list only if the removal evidence is shown.