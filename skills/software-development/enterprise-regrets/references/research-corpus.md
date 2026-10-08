# Enterprise Regrets — Research Corpus (2026-10-08)

Source bibliography backing the 12 regret-lens patterns in SKILL.md. Each entry
was found via `web_search` (Oct 2026) and summarized into the pattern corpus.
Citations are by platform + thread/article title + year (the PII gate forbids
raw numeric thread IDs, personal names, and non-allowlisted hosts in the public
repo); every title is searchable verbatim to recover the source. Quotes in
SKILL.md are paraphrases of these sources, not verbatim reproductions.

## THEME 1: Microservices / premature distribution
- Hacker News thread "Microservices Killed Our Startup" (2025) — 4-engineer startup split before boundaries were real; lost 6 months and runway; back on monolith = shipping again. "Premature distribution killed the startup, not microservices." Start modular monolith, earn boundaries, then extract.
- Hacker News thread "Why Twilio Segment moved from microservices back to a monolith" — 140 services, shared-library version hell → distributed monolith; all the network cost, none of the isolation benefit.
- Hacker News thread "Death by a Thousand Microservices" — ≥25% of engineering time maintaining the platform; complexity is far easier to add than to remove (reverting microservices ≈ ground-up rebuild).
- Hacker News thread "The Prime Video microservices to monolith story" — boring stack (MySQL/PHP) still stable years later while flashy-stack startups died; rewrites rarely succeed, teams blame the language not themselves.
- Hacker News thread "We turned our monolith into microservices 6 years ago" — a "one year" rewrite became a 7-year transition threatening revenue; "the mistake was having an architect who is not shipping product."
- Hacker News thread "How about just stop making microservices and go back to..." — microservices = a technical solution to a people problem; until ~20 backend engineers, no point.
- r/ExperiencedDevs thread "What's the fastest you've gone from an irreversible decision to regretting it?" — day-0 Kafka + event sourcing + CQRS for a CRUD admin + ledger; 7 containers to update one field; regret instant and not reversible (domain language baked into event stream).

## THEME 2: The Big Rewrite
- "Things You Should Never Do, Part I" (joelonsoftware.com, 2000) — "the single worst strategic mistake that any software company can make"; Netscape rewrote its browser, never shipped v5, handed the market to IE.
- potapov.dev "Why Big Rewrites Fail" — 25-year pattern: big-bang replacement + feature freeze + timeline doubles; second-system effect balloons scope; successful modernizations kept shipping (strangler fig). "The burden of proof is on the rewrite, not the incremental path."
- potapov.dev "To Rewrite or Not to Rewrite: A Decision Guide" — the business-value kill question; heuristic: knowledge on the team → can rewrite, knowledge only in code → must refactor; two-hats rule, characterization tests first.
- codefol.io "The Exercise that Tells You if your Big Rewrite Will Work" — a new design ends up roughly the same shape as the old one; if you can't see what the architecture SHOULD be, rewriting won't fix it; a divided-up rewrite beats a 100% one.
- Medium "We Rewrote Our App in React. Two Years Later, We're Back on jQuery" — $200K rewrite was slower and buggier, reverted in 12 days. Lessons: boring tech wins; Stack Overflow trends ≠ right choice; dev experience ≠ user experience; rewriting almost always wrong.
- mbharris.co.uk "Why you should never do the big rewrite, even using Agile" — 18 months, delivered a low-value search tool late; tech lead left; legacy is legacy due to lack of tests / how it's written, not the language.
- SEMastery "What Rewriting a 40-Year-Old Project Taught Me About Software Development" — >70% of large legacy rewrites fail (Standish/Gartner); the moving-target problem; Chesterton's Fence (find the why before removing); characterization tests; strangler pattern.
- blog.mikebowler.ca "The Big Rewrite" — technical bankruptcy: deferring quality until the team gives up; rewriting without changing practices = same result the second time; Scouting Rule (leave code a little better each time).

## THEME 3: Database choices (least reversible)
- r/SaaS thread "Started with MongoDB because it was trendy. Migrated to Postgres after 18 months." — flexible schema wasn't needed once the model stabilized; 6-week migration, 4h downtime, 3.2M rows, 3-5x faster, cheaper.
- Medium "We Replaced PostgreSQL with DynamoDB and Regretted It" — AWS bill $3.2K → $18.4K in a month; $200K over 6 months. "Database choices aren't just technical decisions — they're financial commitments that compound."
- iamanuragh.in "RDS vs DynamoDB: The Database Choice That'll Keep You Up at Night" — chose DynamoDB without an RDBMS eval; ad-hoc filters/reporting/JOINs forced a $12K, 3-week migration back to RDS. "Choosing the wrong database is worse than picking a bad language."
- annpastushko.substack.com "Do you really need single-table design for DynamoDB?" — single-table forces one capacity mode/backup/TTL for everything (3x bill); no per-entity alarms; new devs take weeks on composite keys; adding a GSI = migrate every item.
- r/SaaS thread on an events table with no retention policy — starts as an audit trail, a feature writes to it in a loop, one day it's bigger than the rest of the DB and you do emergency cleanup while everything is slow.

## THEME 4: Cloud migration — BOTH directions can be regrets
- 37signals / Basecamp cloud-exit write-ups (2023-24) — $3.2M/yr AWS → ~$1.3M after repatriating to own hardware; ~$700K Dell investment recouped in <18 months; ~$10M projected savings over 5 years; 99.99% uptime. "Never fully apples-to-apples."
- GEICO "Project Boomerang" (inspectural.com analysis) — cloud costs 2.5x over budget; microservices → explosive inter-service data-transfer fees; repatriated steady-state workloads (policy/claims DBs, customer data, analytics) to private cloud: 65% cost cut, $325M/yr projected, 14-month payback, 40% faster. Kept cloud only for burst/edge.
- johal.in "Why We Ditched Cloud-Native for On-Prem Servers (And Regretted It)" — 12 services off EKS to a colocated rack "to save 60%"; six months later $210K in unplanned hardware/headcount/downtime, p99 tripled, deployment frequency -57%. On-prem TCO 2.8x AWS. "Never trust a cost-saving projection that doesn't include operational overhead."
- Medium "We Spent $2M Leaving AWS. Then $3M Coming Back." — repatriated to colo; model assumed 95% utilization, actual 45%; elasticity avoids over-provisioning; "cloud isn't expensive, incompetence is"; FinOps (better cost management) cut costs 35-45% without moving a server.

## THEME 5: Premature optimization / premature abstraction / YAGNI
- dev.to "When Abstraction Becomes a Bottleneck: The Real Cost of Overengineering" — the asymmetry: removing a premature optimization is localized; removing a premature abstraction ripples through the entire codebase.
- r/buildinpublic thread "What technical decision did you regret after scaling your SaaS?" — bad DB structure, skipped auth/security, no logging/monitoring, hardcoded everything, "temporary fixes" becoming permanent; technical regrets usually come from premature optimization.
- r/ExperiencedDevs infrastructure thread — "the biggest infrastructure regret I see is premature complexity: Postgres + Redis + a message queue when your app gets 100 requests/day." One codebase and one database.

## THEME 6: Enterprise infrastructure decisions (endorse/regret ledger)
- cep.dev "(Almost) Every Infrastructure Decision I Endorse or Regret after 4 Years Running Infrastructure at a Startup" (2024) — Endorse: AWS over GCP, EKS, GitOps/Flux, Terraform, Karpenter, Ubuntu dev servers, PagerDuty. Regret: EKS managed addons, AWS premium support (≈ another engineer's salary), multiple apps sharing one database, not adopting an identity platform early, not using OpenTelemetry early, Renovatebot complexity, SealedSecrets, not more code-ish IaC. "With rare exception, never regretted writing automation or documentation." "Less is better."
- Hacker News thread on the above — "every infrastructure decision is probably going to have regrets over a 4-5 year timeframe"; I shouldn't have chosen Python 2 in 2007, Angular 2 in 2011, Java/MySQL in 2019.

## THEME 7: Hiring / outsourcing / consultants
- Hacker News "Ask HN: Do you have a software consultant or outsourcing horror story?" — $80K to a dev firm that fronted for overseas work; 16 people × 60h/wk × 12 weeks produced only UI templates with no logic underneath; nobody in-house understood the product. Counter-lessons: small paid trial, meet the actual team, staged payments, keep someone in-house who owns the product.
- r/Entrepreneurs "Non-technical founder here. Burned $40k+ on the wrong tech hires" — hired a part-time engineer from a top company: mediocre code, terrible communication, runway cut in half. "Credentials don't matter, delivery does." Cut it if they can't deliver in 1-2 months.
- r/ExperiencedDevs interviewer horror stories — tech lead with 15 yrs experience couldn't code or lead; 2 years of hell before firing because a non-technical manager thought he spoke well.
- Seedcase Project "Lessons learned from working with software consultants" — hire consultants to TRAIN in a specific agreed area, for a short period (2-3 months, not 6), to help design not build.
- Globalbit "Outsourcing QA: An Honest Framework for CTOs" — "Communication gaps. Not skill gaps. Every failed outsourcing engagement traces back to insufficient communication structures." Internal domain knowledge must be codified enough that a stranger can judge correctness.
- Tasrie case study "How a Mid-Market SaaS Company Saved $253K on Kubernetes Migration" — 6 months, $420K, zero production workloads, 2 senior engineers about to quit; consultants finished in 4 months for $239K. "The architecture decisions you make in week 1 determine whether your migration costs $200K or $600K."

## THEME 8: Early tech decisions are sticky
- r/programming "The disproportionate influence of early tech decisions" — "never seen a POC not become the product"; it's hard to replace old systems because nobody knows all the jobs they do anymore (requirements E, F, G forgotten; H necessary on Tuesdays; I for that one customer; J maybe still used, implementers gone).
- r/founder "Founders: What's one decision you deeply regret?" — waiting too long to let someone go; a part-time cofounder is a hobbyist, not a partner; underestimated leadership.

## THEME 9: Enterprise IT executive regrets
- Computerworld "Worst Decisions" (2004) — a county CIO: "giving in to requests to rewrite a system without insisting that business process be redesigned as a first step." Multiple CIOs: rewrites, vendor choices, outsourcing the crown jewels.

## Cross-cutting patterns derived for the skill
1. Irreversibility is the real risk: DB/data-model choices are the least reversible (weeks-months, $$$); code style is most reversible.
2. Complexity is asymmetric: easier to add than remove; getting microservices/abstractions/event-streams OUT ≈ ground-up rebuild.
3. The business-value test kills most "clean-up" rewrites: "what value does this bring to the business?"
4. Knowledge transfer beats code: institutional knowledge lives in code/comments/heads; rewriting discards scar tissue.
5. Boring tech wins: battle-tested, hireable, predictable. Trend-chasing (MongoDB, microservices, latest framework) is the root of most regrets.
6. Cost models lie: TCO must include ops headcount, failure handling, over-provisioning, opportunity cost of zero-feature periods. Both cloud→on-prem and on-prem→cloud have been regrets.
7. Team/organization problems masquerade as technical problems: microservices = a people problem; "architect who doesn't ship" = organizational failure.
8. Early decisions are sticky: POC becomes product; vendor lock-in grows with every integration; identity/security/logging/monitoring deferred = expensive later.
9. Test/verify/characterize before changing legacy: tests are the safety net that makes incremental improvement safe.
10. Premature abstraction is worse than premature optimization: localized vs systemic removal cost.
11. Keep dependencies up to date early; version drift is a compounding tax.
12. Communication gaps fail more projects than skill gaps; a small paid trial beats credentials; someone in-house must own the product.
