---
name: social-media-analyzer
version: 1.0.0
description: "Social media campaign analysis and performance tracking. Calculates engagement rates, ROI, and benchmarks across platforms. Use when analyzing social media performance, calculating engagement rate, measuring campaign ROI, comparing platform metrics, or benchmarking against industry standards. Also use when the user mentions 'social media audit,' 'engagement rate,' or 'which platform performs best.'"
triggers:
  - "social media analytics"
  - "social media analysis"
  - "social media report"
---

## Core Formulas
- **Engagement rate** = (engagements ÷ impressions) × 100. Engagements = likes + comments + shares + saves + clicks (define per platform; exclude paid-reach inflation when judging organic).
- **Reach vs impressions** — reach = unique people who saw the post; impressions = total displays (incl. repeat views). An impressions/reach ratio above ~2 means the same audience sees content repeatedly.
- **ROI per platform** = (attributed revenue − spend − content cost) ÷ spend × 100. Attribute revenue via UTMs, promo codes, or platform pixel data.

## Workflow
1. **Pull data** from native insights (Meta Business Suite, X Analytics, LinkedIn Analytics, TikTok Analytics, YouTube Studio, Instagram Insights) or exported platform CSVs.
2. **Normalize** into one table: platform, post date, reach, impressions, engagements by type, clicks, spend, conversions. Use ISO dates and one consistent engagement definition.
3. **Compute metrics** — engagement rate, reach/impressions ratio, CPM, CPC, cost per engagement, ROI per platform.
4. **Benchmark** — compare against industry medians (below) and your own trailing 4-week average.
5. **Competitor comparison** — track 3-5 competitors' post frequency, engagement rates, and content mix; note their top 3 posts per week and the pattern they share.
6. **Report** — lead with the metric that maps to the business goal (sales, leads, brand lift).

## Benchmarks by Industry (indicative medians, engagement rate)
- Retail/E-commerce: 0.5-1.5% (Instagram/Facebook), 1-3% (TikTok)
- B2B/SaaS: 1-3% (LinkedIn), 0.5-1% (X)
- Media/Publishing: 1-2% across platforms
- Hospitality/Travel: 1-2.5% (Instagram)
- Nonprofit: 1-3% (Facebook)

Benchmarks shift by year, algorithm, and audience size — always pair with your own trailing average.

## Reporting Template
**Weekly (ops)**: per-platform table — posts, reach, impressions, engagement rate, top 3 posts (with what worked), spend, CTR, action items.
**Monthly (strategy)**: 4-8 week trend lines, engagement rate vs. benchmark, ROI per platform, audience growth, share of voice vs. competitors, 3 insights + 3 recommendations, next month's experiment.

## Data Sources
- Native insights per platform (most accurate audience + engagement data).
- Exported CSVs from ad managers for spend/CPM/CPC.
- UTM-tagged links in GA4 for conversion attribution.
- Social listening tools for share of voice and sentiment (see the brand-intelligence skill).
- Manual spreadsheet consolidation when API access is unavailable; document the export date.

## Pitfalls
- Don't compare engagement rates across platforms — baselines differ wildly.
- Don't count impressions as reach; it inflates "seen by" claims.
- Exclude boosted-post metrics when judging organic content quality.
- High CTR + low conversion = content/audience mismatch, not success.
