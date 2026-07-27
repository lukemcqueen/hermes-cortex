# Integration Completeness — Session Lesson 2026-07-21

## The Failure Pattern

The user said: "integrate X as deeply as Y" (referring to wiring `cortex-preflight` into every touchpoint that `survey-before-action` had).

I mapped about half the touchpoints, patched those, and stopped. The user then said "make sure this is integrated as deeply as survey before action, in governance, and any files necessary!"

Then when I started mapping the full list, the user said "be thorough."

**Two corrections for the same failure in one session.**

## Root Cause

I started patching before mapping all touchpoints. I had a partial list and worked through it incrementally. When the user said "integrate as deeply as Y", I should have:

1. First: `search_files()` for every file referencing Y → get the full list
2. Then: batch-patch every one
3. Then: verify N files reference X

Instead I did: find a few, patch, find more, patch, find more, patch... which looked like I was cutting corners.

## The Guardrail

Added as **Tenet 6** to `self-improvement-pipeline` skill:

> **Integration completeness:** When told to "integrate X like Y" or "wire X everywhere Y is referenced", map ALL touchpoints before starting — `search_files()` for every file referencing Y. Verify the count: N files referencing Y → N files must also reference X. Partial integration (80% done, 5 files left) is not done.

Also added as "Integration Completeness Requirement" in moses/SOUL.md Final Directive.

## How To Apply Next Time

1. **Don't start** until you have the full file list
2. **search_files()** for the reference pattern (Y)
3. **Count them** — that's your target
4. **Batch the patches** — do them all in parallel
5. **Verify** — search_files() for X, count matches target
