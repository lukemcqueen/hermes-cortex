---
name: campaign-analytics
version: 1.0.0
description: "Analyzes campaign performance with multi-touch attribution, funnel conversion analysis, and ROI calculation for marketing optimization. Use when analyzing marketing campaigns, ad performance, attribution models, conversion rates, or calculating marketing ROI, ROAS, CPA, and campaign metrics across channels."
triggers:
  - "campaign analytics"
  - "campaign performance"
  - "multi-touch attribution"
  - "campaign roi"
---

## When to Use

Use when analyzing marketing campaign performance: multi-touch attribution, funnel conversion analysis, ROI/ROAS/CPA calculation, channel comparison, or deciding what to optimize next. Works with data from ad platforms (Google/Meta/LinkedIn/X), GA4, CRM, or a single export the user provides.

## Workflow

### 1. Attribution Model Selection
Choose a model based on the buying cycle:
- **First-touch:** credit = first interaction. Use to evaluate top-of-funnel / discovery value.
- **Last-touch:** credit = converting interaction. Use for bottom-of-funnel / retargeting evaluation (platform default in most ad dashboards).
- **Linear:** credit split equally across all touchpoints.
- **Time-decay:** credit decays with touchpoint age; common formula `weight(t) = 2^(-t/half-life)` where t = days before conversion and half-life ≈ 7 days.
- **U-shaped (position-based):** 40% first touch, 40% last touch, 20% split across middle touches.
Apply one model consistently across the whole reporting period; never mix models when comparing channels.

### 2. Funnel Conversion Analysis
1. Define stages (e.g., Impressions → Clicks → Landing visits → Sign-ups → Purchases → Repeat).
2. Stage conversion rate: `CVR = stage_out / stage_in × 100`. Example: 10,000 impressions → 500 clicks = 5% CTR; 500 clicks → 25 purchases = 5% CVR; overall impression → purchase = 0.25%.
3. Compute drop-off per stage (`100% − CVR`) and rank by magnitude; the biggest drop is the primary optimization target.
4. Segment the funnel (device, channel, campaign, new vs returning) to find where segments diverge.

### 3. Core Formulas (worked examples)
- **CPA = Spend / Conversions.** Spend $2,000, 40 conversions → CPA = $50.
- **ROAS = Revenue / Spend.** Revenue $8,000 on $2,000 spend → ROAS = 4.0 (4:1).
- **ROI = (Revenue − Spend) / Spend × 100.** ($8,000 − $2,000) / $2,000 = 300%.
- **Blended CAC = Total acquisition spend / New customers** (include salary/tools if true CAC is wanted, not just ad spend).
- **Break-even ROAS = 1 / Gross margin.** At 40% margin, break-even ROAS = 2.5 — below that, the campaign loses money even if "profitable" on ad spend alone.

### 4. Channel Comparison Table
Build one row per channel: Spend, Conversions, CPA, Revenue, ROAS, CVR, Notes. Example:

| Channel | Spend | Conv. | CPA | Revenue | ROAS | CVR |
|---|---|---|---|---|---|---|
| Google Search | $2,000 | 40 | $50 | $8,000 | 4.0 | 5.0% |
| Meta | $1,500 | 18 | $83 | $4,500 | 3.0 | 2.2% |
| LinkedIn | $1,000 | 5 | $200 | $1,750 | 1.75 | 1.0% |

Rank by ROAS for efficiency and by volume for scale; the efficiency-vs-scale tradeoff drives the budget-reallocation recommendation.

### 5. Reporting Cadence
- **Daily:** spend, CPA/ROAS vs target, anomaly check (spend spikes, tracking drops).
- **Weekly:** full channel table, funnel drop-offs, attribution results, optimization actions taken.
- **Monthly:** trends, CAC payback, cohort analysis, budget reallocation proposals, forecast vs actual.

## Pitfalls
- Comparing channels under different attribution models (e.g., Google last-click vs Meta 7-day click) — normalize first.
- Ignoring time lag: B2B and luxury purchases convert weeks after first touch; short windows under-credit discovery channels.
- Celebrating ROAS without margin: 3.0 ROAS at 25% margin loses money (break-even 4.0).
- Blind spots: offline sales, cross-device, and organic assist aren't in ad-platform reports — state them as caveats.
- Reporting vanity metrics (impressions/CTR) without tying them to revenue outcomes.

## Verification
- Every number in the report traces to a source (platform export, GA4, CRM) — spot-check 3 figures manually.
- Attribution weights sum to 100% of conversions for every model applied.
- Formulas are internally consistent (e.g., ROAS × spend = revenue within rounding).
- Recommendations name a specific next action, owner, and expected metric impact.
