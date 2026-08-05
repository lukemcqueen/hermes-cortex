---
name: brand-intelligence
version: 1.0.0
description: "Monitor and analyze brand mentions, sentiment, share of voice, and competitive positioning across web/social/review platforms."
triggers:
  - "brand monitoring"
  - "brand mentions"
  - "sentiment analysis"
  - "share of voice"
  - "competitive brand tracking"
---

## When to Use
Use when tracking what people say about a brand (or competitors) across social media, news, forums, and review sites: sentiment analysis, share-of-voice measurement, competitive positioning, or alerting on spikes and crises.

## Monitoring Sources
- **Social**: X/Twitter search, Reddit, LinkedIn, TikTok/Instagram comments and tags, Facebook mentions.
- **Web/news**: Google Alerts, RSS feeds, press and blog mentions (see the blogwatcher skill).
- **Reviews**: Trustpilot, G2/Capterra, Google Business, app store reviews, Amazon.
- **Communities**: forums, public Discord/Slack channels, Hacker News, Product Hunt comments.
- Capture per mention: source, URL, date, author, reach (followers/upvotes), quoted text. Store as structured rows (CSV/JSON) with ISO dates.

## Sentiment Classification
Classify each mention: **positive / neutral / negative**, plus optional intensity (1-5). Rules:
- Positive: praise, recommendation, purchase intent, solved-problem stories.
- Negative: complaints, bug reports, competitor-switch intent, crisis language.
- Neutral: questions, news coverage, factual mentions.
- Auto-classify with keyword lists first, then sample-verify ~20% manually; never trust raw classifier output for crisis detection.

## Share of Voice (SOV)
SOV% = (your brand mentions ÷ total category mentions, incl. competitors) × 100.
- Compute per channel and overall; segment by period (weekly/monthly).
- Read the trend: rising SOV in a growing category is healthy; falling SOV while competitors rise signals positioning erosion.

## Competitor Tracking
- Keep a watchlist of 3-5 competitors; log their launches, pricing changes, campaign themes, and sentiment spikes.
- Compare: mention volume, SOV, sentiment mix, top-performing content themes, review ratings, and response times.
- Monthly: update a competitive positioning table (feature, price, audience, positioning statement).

## Alerting Cadence
- **Daily** (or real-time): negative-spike and crisis keywords (e.g. "outage", "scam", "lawsuit"), brand handle mentions, review drops.
- **Weekly**: digest of all mentions, SOV change, top themes.
- **Monthly**: full report with trends, sentiment shifts, competitor moves, recommendations.
- Escalate immediately: mention volume spike > 3× baseline, sentiment dropping 2+ days, or a top-tier news outlet mention.

## Report Format
Monthly report sections: (1) executive summary, (2) mention volume & SOV by channel, (3) sentiment mix + trend chart, (4) top themes with representative quotes, (5) competitor comparison, (6) crisis/risk watch, (7) 3 recommendations.

## Pitfalls
- Don't count every mention equally — weight by source authority and reach.
- Don't classify sentiment without context (sarcasm, "this brand is dead" jokes).
- Alerts without thresholds cause alert fatigue — set baselines before enabling spike detection.
