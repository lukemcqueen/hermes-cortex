---
name: paid-ads
version: 1.0.0
description: "When the user wants help with paid advertising campaigns on Google Ads, Meta (Facebook/Instagram), LinkedIn, Twitter/X, or other ad platforms. Also use when the user mentions 'PPC,' 'paid media,' 'ad copy,' 'ad creative,' 'ROAS,' 'CPA,' 'ad campaign,' 'retargeting,' or 'audience targeting.' This skill covers campaign strategy, ad creation, audience targeting, and optimization."
triggers:
  - "paid ads"
  - "ppc"
  - "facebook ads"
  - "google ads"
  - "ad campaign"
---

## When to Use

Use when planning, launching, or optimizing paid advertising on Google Ads, Meta (Facebook/Instagram), LinkedIn, or X (Twitter). Covers campaign structure, audience targeting, ad copy/creative, bidding, tracking, optimization loops, and budget allocation. Ask which platform and objective first; the workflow applies per-platform with the platform notes given.

## Workflow

### 1. Define Objective & KPIs
One objective per campaign (traffic, leads, sales, brand). Set targets, e.g., "Lead-gen at CPA ≤ $60" or "Sales at ROAS ≥ 3.0". Every structure decision follows from this.

### 2. Campaign Structure (campaign > ad group > ad)
- **Google Ads:** one campaign per theme/geo; ad groups = tightly themed keyword clusters (10-20 keywords, one intent). Responsive Search Ads (up to 15 headlines / 4 descriptions) for Search; Performance Max for feed-based reach. Match types: broad only with smart bidding, plus phrase and exact.
- **Meta:** Campaign (objective) > Ad Set (audience + placement + budget) > Ad (creative). One ad set per distinct audience angle; 2-3 ads per ad set for testing. Use Advantage+ campaign budget optimization once you have >20 conversions/week.
- **LinkedIn:** Campaign > Ad Group > Ad; objective-based (awareness, consideration, conversion); Matched Audiences for retargeting/ABM.
- **X:** Campaign > Ad Group > Ad; per-objective (awareness, video views, app installs, website clicks/conversions).

### 3. Audience Targeting
- **Google:** keywords + audience signals (in-market, custom intent, remarketing, customer match); layer geo/device/schedule negatives.
- **Meta:** interests, behaviors, custom audiences (pixel/CRM), lookalikes 1-3% (start 1-2%, broaden only if scale-limited). Exclude existing purchasers from acquisition sets.
- **LinkedIn:** job titles, functions, seniority, company size/industry, skills; account lists via Matched Audiences.
- **X:** keywords, interests, follower lookalikes, conversation targeting, retargeting (site visit, engaged).
- Sizing: ≈500k-2M audience is the Meta learning-phase sweet spot — too narrow kills delivery, too broad wastes spend.

### 4. Ad Copy & Creative
- Hook in the first line (benefit, not feature); one CTA per ad; copy matches the landing page message.
- Include the offer, proof (reviews, stats), and genuine urgency. For luxury/mid-premium brands: restraint and craft beat hype — short copy, high-quality imagery, no price anchoring unless it's the strategy.
- Test 3 copy angles × 2 creatives minimum. Refresh creative when frequency > ~2.5-3 (Meta) or CTR decays.

### 5. Bidding
- **Google:** tCPA/tROAS after ≥15-30 conversions in 30 days; Target Impression Share for brand; Manual CPC for tight control during testing. Let automated bidding learn — change targets at most weekly.
- **Meta:** Lowest Cost (volume) vs Cost Cap (control); bid cap when delivery is unstable.
- **LinkedIn/X:** mostly CPC/CPM; switch to platform auto-bidding toward your objective once conversion tracking is solid.

### 6. Tracking (set up before any spend)
- **UTM convention:** `utm_source` (google/meta/linkedin/x), `utm_medium` (cpc/social/paid), `utm_campaign`, `utm_content` (ad id), `utm_term` (keyword). Lowercase, no spaces.
- **Pixels/APIs:** Google Ads tag + Enhanced Conversions; Meta Pixel + Conversions API (CAPI) with `event_id` dedup; LinkedIn Insight Tag; X pixel.
- Verify with a test conversion in each platform's events manager (e.g., Meta Events Manager shows "Active" + test event) and confirm GA4 sees the same events.

### 7. Optimization Loop (weekly)
1. Pull the search-term report (Google) — add negatives, promote exact-match winners into dedicated ad groups.
2. Kill or rebuild ad groups spending >2× target CPA with <0.5× target CVR.
3. Shift 10-20% of budget from lowest-ROAS to highest-ROAS campaign weekly (never more — avoids learning-phase resets).
4. Check frequency, CPM creep, and impression share (lost to budget vs rank) per platform.
5. Log changes; measure their effect for 3-7 days before the next loop.

### 8. Budget Allocation
Start 70/20/10 (proven winners / testing / experimental). Scale winners by ≤20-30%/week to protect auction stability. Pause anything below break-even ROAS after 2× its conversion cycle.

## Pitfalls
- Launching with tCPA/tROAS on zero conversion history — the algorithm has nothing to learn; start manual or volume-based bidding.
- Not excluding converters from prospecting sets (double-serving existing customers).
- Tracking drift: broken pixels or UTM typos silently corrupt optimization — verify monthly.
- Changing budgets/bids daily — learning phases restart and performance swings.
- One ad per ad group — no creative learning; always run 2-3 variants.

## Verification
- Test conversion fires end-to-end (ad → landing page → pixel/CAPI → platform events manager shows the conversion).
- UTM parameters parse correctly in GA4 (source/medium/campaign columns populated).
- Campaigns hit CPA/ROAS targets for 2 consecutive weeks before scaling.
- Optimization log shows date, change, and measured effect for each action.
