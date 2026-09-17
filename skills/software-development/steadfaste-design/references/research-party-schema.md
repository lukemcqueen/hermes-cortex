# Grounded research "party" — standard task prompt + output schema

Use for VALIDATES/BORROW/GAP-RISK design reviews. One `delegate_task` call with several tasks (one per DOMAIN CLUSTER), all dispatched together so they run in parallel. Each subagent is instructed: return structured findings, read PRIMARY docs, no file writes, mark UNKNOWN rather than guess.

## Task prompt skeleton (per cluster)

    Research [DOMAIN] and compare against [steadfaste component].
    Cover at least: [must-cover list].

    For EACH solution report:
    - what it actually provides (mechanism, not marketing)
    - how it compares to [steadfaste component]
    - a verdict from exactly:
        VALIDATES — what confirms our design is sound (or already-done elsewhere)
        BORROW   — a specific mechanism we should adopt
        GAP-RISK — a weakness in our design this exposes that we have NOT covered
      each = one-line finding + the mechanism (no incident narrative)
    Be specific and grounded (read real docs, cite the source).
    No file writes — return structured findings.
    Mark UNKNOWN rather than guess. Prioritize ACCURACY over coverage.

## Output schema (per cluster)

    {
      "findings": [
        {
          "id": "<slug>", "solution": "<name>", "category": "<domain>",
          "sources": ["<url>"],
          "provides": "<mechanism>",
          "vs_steadfaste": "<comparison>",
          "validates": ["..."],
          "borrow": ["..."],
          "gap_risk": ["..."]
        }
      ],
      "note": "<method + net assessment>"
    }

## Handling partial results (pitfall)
A fan-out can return only PART of the assigned clusters (one returned only 1 of 3;
the missing clusters had to be re-dispatched in a second `delegate_task` call).
Check the returned JSON against the clusters you assigned; re-dispatch exactly the
missing ones rather than assuming a partial result is the whole picture. Do not
act on the full set until every assigned cluster has reported.

## Synthesis
Fold the findings into a dated research doc under `docs/research/`, driven by
your OWN governance cycle (begin_change … end_change), and link it from
`docs/README.md`. A synthesis table of per-system one-line verdicts is the
readable core; keep the rich mechanism detail beneath each row.
