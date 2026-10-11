---
name: job-board-research
version: 1.1.0
category: research
description: "Use when compiling vetted job listings from job boards. Aggregates, verifies each posting against its real JD, and delivers a tiered, linked report."
platforms: [linux, macos]
---

# Job-Board Research — Compiling Vetted Job Lists

Workflow for requests like "find AI jobs in Korea with no Korean requirement":
aggregate listings from multiple boards, verify each posting against the
actual JD, and deliver a filtered, linked, deduplicated report. Never hand-type
a list — deliver a file (`MEDIA:` path) plus an inline highlights summary.

*Absorbs `job-market-research` (merged 2026-10-12): the LinkedIn guest-search
mechanics and bot-wall fallback lived only there, the throttling and JD
verification only here.*

## Procedure

### 1. Source board inventory

Run searches to find curated boards before scraping generic ones:
- Curated English-JD boards (e.g. Seoulstart `/jobs/english-jobs`, Dev Korea, dev-korea.com) — highest signal for language-friendly filters (explicit English JD = no Korean required).
- LinkedIn guest search — biggest volume; paginates via `&start=N` (25/page, stops serving beyond ~100–150 per query). Run 2–3 keyword queries and merge.
- Company career pages only when the aggregator mirrors them; direct pages (Coupang) may be Cloudflare-walled — use the aggregator instead of fighting the WAF.

### 2. Scrape the data layer, not the rendered page

- Check raw HTML for `<script type="application/ld+json">` with `"@type":"ItemList"` — most job boards embed full item data (`{"@type":"JobPosting",...}` with title, org, location, apply URL, datePosted, description). Sites carry several LD+JSON blocks; a broad `<script>` match grabs the wrong one and yields zero jobs while looking successful. Anchor the regex on `"@type":"ItemList"`, skip pages where it is absent, and verify on one page before looping all pages.
- Paginate via URL parameter with `requests` + 0.3–0.5s sleep; only fall back to browser DOM scraping when data is client-rendered (or `requests` gets 403).
- LinkedIn guest job pages (no login): cards are `li a[href*="/jobs/view/"]` + `.base-search-card__title` + `.base-search-card__subtitle` — extract via one `js()` IIFE returning JSON. The description lives in `div.show-more-less-html__markup`; a plain requests fetch works without login.
- A company-specific query (`keywords=<Company> machine learning`) surfaces roles the generic keyword search missed.
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
4. Non-LinkedIn sources (Ashby, Greenhouse, company boards) are usually fetchable via plain requests even when an aggregator is walled — check them individually instead of marking the whole posting unverified.

### 5. Dedupe, then deliver a tiered report

Dedupe on `(title[:70], company)` **before** counting — titles repeat verbatim
across pages and queries, and un-deduplicated counts overstate the result and
break the "N roles across M companies" header assertion.

Write a markdown file with:
- **Tier 1 — fully verified**: language-clean JDs, direct apply links, grouped by company.
- **Risky tier** — local-language JDs with no explicit fluency requirement; label "confirm with recruiter".
- **Excluded** — what was removed and the evidence phrase that removed it, so the filter is auditable.
- Counts in the header, caveats stated (English JD ≠ guaranteed no-Korean).
- Deliver via `MEDIA:` path in chat; give a short inline highlights list, not the full dump.

## Pitfalls

- **Don't classify from titles alone** — half of English-titled postings carry a local-language requirement buried in the qualifications section.
- **A generic JSON-LD regex can match site-metadata blocks** (WebSite, Organization scripts) — anchor on `"@type":"ItemList"` and skip pages where it is absent.
- **Bot-walled career sites (Cloudflare interstitial):** do not retry the same URL hoping it clears — fall back to a source that carries the same jobs (LinkedIn guest search with the company as keyword) and note the blocked source in the delivery.
- **`browser_exec` and `execute_code` are separate sandboxes** — files written in the browser workspace are invisible to the execute_code kernel and vice versa. Do all parsing in the environment where the data was fetched, or print the data out instead of assuming a shared filesystem.
- **Count exclusions as well as inclusions** — the user trusts the list only if the removal evidence is shown.
