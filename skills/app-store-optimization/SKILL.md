---
name: app-store-optimization
version: 1.0.0
description: "App Store Optimization (ASO) toolkit for researching keywords, analyzing competitor rankings, generating metadata suggestions, and improving app visibility on Apple App Store and Google Play Store. Use when the user asks about ASO, app store rankings, app metadata, app titles and descriptions, app store listings, app visibility, or mobile app marketing on iOS or Android. Supports keyword research and scoring, competitor keyword analysis, metadata optimization, A/B test planning, launch checklists, and tracking ranking changes."
triggers:
  - "app store optimization"
  - "aso keywords"
  - "app ranking"
  - "app store listing"
---

## When to Use

Use when improving an app's visibility and conversion in the Apple App Store or Google Play Store: keyword research, competitor ranking analysis, metadata optimization (title/subtitle/keywords/descriptions), screenshot and A/B testing, review mining, launch checklists, or tracking ranking changes. Works for iOS and Android — always note which store each finding applies to.

## Workflow

### 1. Keyword Research
1. Pull current ranking keywords from first-party sources first:
   - **iOS:** App Store Connect → Analytics → App Store Search (impressions, taps, conversion by query). Apple Search Ads → Search Terms report for paid-converting terms.
   - **Android:** Google Play Console → Reports → Search terms report (impressions, store listing visits, installs, conversion rate per query).
   - **Search Ads API (iOS):** keyword suggestions endpoint — `GET /v4/campaigns/{campaignId}/adgroups/{adGroupId}/keywords/suggestions?query={term}&limit=10` with `Authorization: Bearer {token}` and `X-AP-Context: orgId` headers (v4/v5). Returns suggested keywords with relevance/matching fields — free discovery of terms users actually search.
2. Enrich with third-party tools (Sensor Tower / AppTweak / App Radar style fields): per-keyword **volume** (monthly search frequency), **difficulty/competition** (how hard to rank), **relevancy** (fit to the app), and **trend** (rising/falling). Without a paid tool, estimate volume from search-term reports and autocomplete frequency.
3. Score candidates: `score = volume × relevancy / difficulty`. Rank, keep the top 20-30; drop terms below your volume floor or relevancy < 0.5.
4. Bucket into head (high volume, hard), mid-tail (moderate volume, winnable), long-tail (low volume, high intent). Target mid-tail for the fastest ranking wins.

### 2. Competitor Ranking Analysis
1. Pick 3-5 competitors (direct + category leaders). Record each one's: title, subtitle, keyword field contents (iOS), description, current rank for your target keywords, rating score and count.
2. Build a keyword × competitor matrix: for each target keyword, note which competitors rank top-10 and which metadata terms win it.
3. Identify gaps: keywords competitors rank for that you don't (highest-ROI additions) and their weaknesses (missing keywords, weak ratings, stale screenshots).

### 3. Metadata Optimization
- **iOS:** Title (30 chars), Subtitle (30), Keyword field (100 chars, comma-separated — no repeats, no spaces after commas, don't repeat title/subtitle words). Front-load the title with the highest-value keyword.
- **Android:** Title (30), Short description (80), Full description (4000), tags. Google indexes the full description; repeat primary keywords naturally 2-3 times, no stuffing.
- Rule: every word in the keyword field must earn its place — remove anything not in your scored top-30. Re-audit quarterly or after major updates.

### 4. Screenshots & A/B Testing
1. Lead with the first 2-3 screenshots — they drive conversion. Show the core value proposition in 5-7 seconds; no feature-list dumps.
2. **iOS:** App Store Connect → Product Page Optimization — up to 3 treatments, 90-day test window; test title, subtitle, screenshots, or icon.
3. **Android:** Google Play Console → Experiments — test listing graphics/descriptions with store-provided traffic.
4. Test one variable at a time; run to statistical significance (p < 0.05; typically 2-4 weeks at your traffic level) before promoting a winner.

### 5. Review Mining
1. Pull all reviews (App Store Connect / Play Console exports, or AppTweak/Sensor Tower summaries).
2. Tag by theme: feature requests, bugs/crashes, pricing complaints, praise. Extract the exact phrases users use — they are keyword and description copy gold.
3. Prioritize by volume; feed the top 3 recurring themes into the next release/description update. Reply to 1- and 2-star reviews within 48h (rating impact + ranking signal).

### 6. Ranking Tracking
Re-check target keyword positions weekly (Sensor Tower/AppTweak keyword rankings, or manual App Store/Play search). Log movement and correlate with metadata/version changes to learn what moved the needle.

## Pitfalls
- Keyword-stuffing the title/keyword field (repeats, irrelevant terms) — Apple/Google can suppress rankings and it wastes the 100-char budget.
- Ignoring localization: keywords behave differently per locale; optimize each storefront separately, never translate literally.
- Chasing head terms you can't win: a top-50 rank on a huge term beats rank 200; win mid-tail first.
- Treating screenshots as an afterthought — conversion rate (impression → install) multiplies every ranking gain.
- Trimming the iOS keyword field without re-verifying: the field is evaluated as a whole; after changes, re-check rankings within 2-4 weeks.

## Verification
- Confirm metadata changes are live in App Store Connect / Play Console and respect character limits (30/30/100 iOS; 30/80/4000 Android).
- Export search-terms reports before and after the change; verify target keywords' impressions and conversion improved or held after 2-4 weeks.
- A/B tests produced a statistically significant winner with a documented lift (e.g., +8% conversion) before promotion.
- Review replies logged; theme counts captured and the top 3 themes fed into the next iteration.
