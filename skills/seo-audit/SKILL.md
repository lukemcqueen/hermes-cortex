---
name: seo-audit
version: 1.0.0
description: "Use when the user wants to audit, review, or diagnose SEO issues on a site: rankings, technical SEO, on-page, backlinks, Core Web Vitals, site speed."
triggers:
  - "seo audit"
  - "seo analysis"
  - "technical seo"
  - "site audit"
  - "core web vitals"
  - "seo issues"
  - "site speed"
---

## When to Use

Use when the user wants to audit, review, or diagnose SEO issues on a site: rankings, technical SEO, on-page, backlinks, Core Web Vitals, site speed. Produces a priority-ordered fix list an agent or developer can execute from.

## Workflow

### 1. Crawl Audit (Screaming Frog style)
Crawl the site and check every URL for:
- **Titles:** present, unique, 50-60 chars, keyword-front-loaded. Flag missing, duplicate, or truncated.
- **Meta descriptions:** present, unique, 150-160 chars (not a direct ranking factor, but drives CTR).
- **H1:** exactly one per page, unique, contains the primary keyword. Flag multiple, missing, or duplicated H1s.
- **Canonicals:** self-referencing where intended; flag canonicals pointing to 404s, redirects, or other domains.
- **robots.txt:** reachable, no `Disallow: /` on important sections, not blocking CSS/JS.
- **sitemap.xml:** valid XML, referenced in robots.txt, contains only 200-status URLs, no noindex pages.
- **Status codes:** flag 404s (fix or 301), 5xx (server issues), 3xx chains (more than one hop), soft-404s (200 pages saying "not found").
- **Redirects:** chains and loops; 301 (permanent) not 302 for moved pages; update internal links to final URLs.
Commands: Screaming Frog CLI — `java -Xmx4g -jar screamingfrogseospider.jar --crawl https://your-domain.com --output_folder ./crawl`; or `curl -sI https://your-domain.com/page` per URL for status checks.

### 2. On-Page & Content
1. **Keyword mapping:** map every important page to its target keyword (one primary + 2-3 secondary). Flag pages with no clear target and keywords with no page.
2. **Content gaps:** for each keyword, compare your page against the top 5 ranking results — missing sections, thinner content, weaker internal linking. Prioritize gaps on money pages first.
3. **Internal linking:** every page needs ≥2-3 internal links with descriptive anchor text; fix orphan pages (crawl "Inlinks = 0").
4. **Structured data:** check JSON-LD (Product, Article, FAQ, Breadcrumb, Organization) via the Rich Results Test or `curl -s https://your-domain.com/page | grep -c 'application/ld+json'`; validate each schema against its spec.

### 3. Technical SEO
- **Core Web Vitals:** LCP < 2.5s, INP < 200ms, CLS < 0.1 (75th percentile, mobile). Measure with the PageSpeed Insights API — `https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://your-domain.com&strategy=mobile` — or `npx lighthouse https://your-domain.com --only-categories=performance`.
- **Mobile:** responsive viewport, tap targets, no horizontal scroll; verify in device mode.
- **HTTPS:** valid cert (no expiry warnings), no mixed content (http resources on https pages).
- **Indexability:** pages meant to rank are indexable (not noindexed, not blocked by robots); check via `site:your-domain.com` or Search Console URL Inspection.

### 4. Off-Page (Backlinks)
Pull the backlink profile (Ahrefs/Semrush/Moz, or Search Console Links report if no paid tool): referring domains, total links, anchor text distribution, link velocity. Flag toxic/spam domains (disavow only the clearly spammy ones), over-optimized anchor text, sudden link drops (penalty vs lost links — investigate), and top pages by referring domains (your linkable assets).

### 5. Priority-Ordered Fix List
Rank fixes by impact × effort:
1. **P0 (this week):** indexability blockers (accidental noindex/robots blocks), crawl errors on money pages, broken checkout/critical 404s, mixed content.
2. **P1 (this month):** title/meta/H1 issues, redirect chains, sitemap hygiene, LCP/INP/CLS fixes on the top 20 traffic pages.
3. **P2 (next quarter):** content gaps, internal linking, structured data rollout, disavow toxic links.
Deliver as a table: Issue | Pages affected | Evidence (URL/check) | Fix | Priority.

## Pitfalls
- Auditing only the homepage — crawl the whole site; half the issues hide on deep pages.
- Confusing "crawlable" with "indexable" — a page can be crawled yet blocked from indexing (noindex/robots).
- Treating lab data as user experience — use field data (CrUX) for the real picture.
- "Fixing" 404s by deleting pages — 301 to the closest relevant page to preserve equity.
- Over-disavowing backlinks — Google ignores most disavows and the wrong ones can hurt; only clearly spammy links.

## Verification
- Re-crawl after fixes: flagged counts for each check class drop to zero (or documented exceptions remain).
- `curl -sI` confirms 301s land on final URLs with no chains; sitemap URLs all return 200 and are indexable.
- PageSpeed/CrUX shows LCP < 2.5s, INP < 200ms, CLS < 0.1 on fixed pages (75th percentile, mobile).
- Search Console: indexed pages trend up; every P0 item on the fix list is closed with evidence.
