---
name: job-market-research
version: 1.0.0
category: research
description: "Use when compiling job listings from web boards."
platforms: [linux, macos]
---

# Job Market Research — Structured Board Scraping

Compile real, linked, deduplicated listings; never hand-type a list. Deliver a file (MEDIA: path) plus an inline highlights summary.

## Procedure

1. **Gather sources in parallel** — one curated English-friendly board (if relevant: seoulstart.com English-JD, dev-korea.com), LinkedIn guest search, and 2-3 web_searches for the domain. Curated boards are small but highest signal (explicit English JD = no Korean required); LinkedIn gives volume.

2. **Prefer JSON-LD over DOM parsing.** Most modern job boards embed a `<script type="application/ld+json">` block with `{"@type":"ItemList","itemListElement":[{"item":{"@type":"JobPosting",...}}]}` containing title, company, location, URL, and datePosted. Extract with a targeted regex (anchor on `"@type":"ItemList"`, not a generic greedy script match) and `json.loads` — one clean parse beats fragile innerText walking. Verify on one page before looping all pages.

3. **Paginate via HTTP `requests` inside the browser session when possible** (session cookies + full HTML, ~0.3s/page sleep); fall back to browser navigation only if requests gets 403.

4. **Bulk-harvest LinkedIn without login (guest search):**
   - URL pattern: `https://www.linkedin.com/jobs/search?keywords=<kw>&location=<loc>&start=<0,25,50...>`
   - Extract per card: `li a[href*="/jobs/view/"]` + `.base-search-card__title` + `.base-search-card__subtitle` via one `js()` IIFE returning JSON.
   - Stop when a page returns 0 cards (guest view caps around ~100-150 results per query). Run 2-3 keyword queries and merge.
   - Company-specific query (`keywords=<Company> machine learning`) surfaces roles the generic keyword search missed.

5. **Dedupe on `(title[:70], company)`** — titles repeat verbatim across pages and queries.

6. **Filter and classify:** keyword-match titles (and description head) for the requested domain; flag postings whose titles contain Hangul/CJK as likely requiring that language — never silently include or silently drop them.

7. **Write the deliverable:** markdown grouped by company, one direct link per role, counts in the header ("N roles across M companies"), caveats stated (English JD ≠ guaranteed no-Korean). Save to a real path and attach via `MEDIA:`; give a short inline highlights list, not the full dump.

## Pitfalls

- **Bot-walled career sites (Cloudflare interstitial):** do not retry the same URL hoping it clears — fall back to a source that carries the same jobs (LinkedIn guest search with the company as keyword) and note the blocked source in the delivery.
- **browser_exec and execute_code are separate sandboxes** — files written in the browser workspace are invisible to the execute_code kernel and vice versa. Do all parsing in the environment where the data was fetched, or print the data out instead of assuming a shared filesystem.
- **Dedupe before counting** — paginated boards serve the same role on multiple pages; un-deduplicated counts overstate the result and break the "N roles" header assertion.
- **A generic JSON-LD regex can match site-metadata blocks** (WebSite, Organization scripts) — anchor the regex on `"@type":"ItemList"` and skip pages where it is absent.
