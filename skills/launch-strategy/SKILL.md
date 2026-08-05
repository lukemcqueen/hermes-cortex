---
name: launch-strategy
version: 1.0.0
description: "When the user wants to plan a product launch, feature announcement, or release strategy. Also use when the user mentions 'launch,' 'Product Hunt,' 'feature release,' 'announcement,' 'go-to-market,' 'beta launch,' 'early access,' 'waitlist,' 'product update,' 'GTM plan,' 'launch checklist,' or 'launch momentum.' This skill covers phased launches, channel strategy, and ongoing launch momentum."
triggers:
  - "launch strategy"
  - "product launch"
  - "go to market"
  - "gtm"
---

## Launch Types
- **Soft launch** — limited audience, low fanfare. Goal: validate product-market fit and fix issues before wider release. Track activation and retention, not press.
- **Hard launch** — full public release with coordinated marketing. Goal: maximize day-one visibility, waitlist conversion, and press coverage.
- **Beta / early access** — invite-only or waitlist-gated. Goal: collect feedback, build community, and generate testimonials/social proof before GA.
- **GA (general availability)** — official commercial release; pricing live, support ready. Goal: sustained growth, conversion, revenue.

Pick the type based on product maturity, support capacity, and the size of the audience you can actually serve well on day one.

## GTM Checklist
1. **Positioning** — one sentence: who it's for, what problem it solves, why it's different. Validate against the top 3 competitors.
2. **Pricing** — set tiers, anchor against competitors, decide trial/freemium, define upgrade paths. Test the pricing page copy with 5 users.
3. **Channels** — pick 2-3 primary channels (X/Twitter, LinkedIn, newsletters, communities, ads); assign an owner and content calendar per channel.
4. **PR / Product Hunt** — draft press release and pitch list; schedule Product Hunt for Tuesday–Thursday (12:01am PT); prepare founder comments and a launch post.
5. **Email sequence** — 5-7 emails: teaser → launch announcement → deep dive → social proof → objection handling → last call → post-launch survey/NPS.
6. **Launch day ops** — go/no-go checklist: links live, analytics installed, support coverage, status page, social scheduled, team briefed, incident playbook ready.
7. **Post-launch 30-day plan** — week 1: fix critical feedback, respond to every mention; week 2: publish case studies/testimonials; week 3: double down on the best channel, run retargeting; week 4: retrospective, iterate on the funnel.

## Risk List
- Traffic spike crashes checkout/signup → load test, autoscale, kill switch.
- Press gets the wrong positioning → pre-brief 3 friendly journalists, approve assets.
- Pricing backlash → publish pricing rationale, offer a grace period for early users.
- Support overwhelmed → FAQ page, canned responses, triage SLAs.
- Launch date slips → build in a 2-week buffer; communicate delays early.

## Metrics
- **Activation** — % of new signups reaching the "aha" moment (first value event) within 24h. Target 25-40% depending on category.
- **Waitlist conversion** — % of waitlist invites that become active users; diagnose drop-off at invite → signup → activation.
- **NPS** — survey 1 week post-activation; segment promoters/detractors and route detractors to support.
- Also track: day-1 signups, activation-to-paid conversion, 30-day churn, and channel CAC.

## Pitfalls
- Don't hard-launch before beta validation — bad reviews compound fast.
- Don't judge the launch on day-1 numbers alone; the 30-day trend matters more.
- Don't skip the go/no-go check — a broken checkout on launch day is the most common disaster.
