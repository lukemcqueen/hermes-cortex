# Delegated Design Review — Elicit + Party via Pro-Model Subagents (user absent)

Validated 2026-08-24: deep-mode elicit + 6-role HC-Party run entirely via
`delegate_task` subagents on the delegation-pinned model (deepseek-v4-pro),
producing the decision + plan for AXI adoption in Hermes Cortex. Use this
recipe when the user asks for a design review but is not available for Q&A,
or when the design should run on a stronger model than the session default.

## Why delegate

- Children inherit the delegation model pin (`delegation.model` in
  config.yaml) — the design runs on the pro model regardless of the
  session model.
- Children cannot ask the user questions — which is exactly right here:
  you provide the answers in context and label your assumptions.

## Recipe

### 1. Elicit (one subagent, deep mode)
- Brief must include: the skill to load (`requirements-elicitation`), the
  domain context, ALL constraints, stakeholders, the success metric, and
  the instruction to self-answer the question bank with every assumption
  labelled `[ASSUMPTION]`.
- Output contract: `output_schema` with `doc_content` (the FULL markdown
  document) + `summary` (counts: total/must/should/could/wont, stories,
  open questions, top requirements).
- **Do NOT have children write files** — their `write_file` can hit the
  always-skills marker gate; return content via the schema and the parent
  places it. This also keeps the parent's context clean (read the returned
  doc from the saved summary file if large).

### 2. Party (6 role subagents in parallel)
- One `delegate_task` batch, 6 tasks: Architect, Security Engineer, SRE,
  Domain Expert, Product, QA (see `architecture-review` skill for role
  focus + default weights 20/20/15/15/15/15).
- Each brief: the role, the decision under review, the 2–4 approaches
  (described concretely with real file paths), the non-negotiable
  constraints, role-specific context nuggets (owner values, existing
  precedents, real violation examples), and the instruction to load
  `architecture-review` and judge independently.
- Output contract per role: `output_schema` JSON — `role`, `scores`
  (1–10 per option), `rationale` (2–4 sentences per option),
  `showstoppers`, `mitigations`. This makes the matrix computable.
- Tell each role explicitly: "Do NOT coordinate with other roles —
  independent judgment."

### 3. Assemble (parent)
- Compute the weighted matrix in CODE (don't eyeball): Σ score × weight;
  print the table + weighted totals.
- Conflict scan: any option where two roles differ by ≥3 → run the
  resolution protocol (dueling briefs → mediated re-scope → re-score).
  Typical resolution pattern: the disagreement is about *which parts of an
  option to adopt now* — fold the winner's good ideas into the runner-up
  and defer the rest with an explicit gate.
- Cost estimate bracketed (optimistic/likely/pessimistic) per option:
  dev effort, infra/month, maintenance hrs/wk, confidence.
- Write the decision doc (private repo `docs/design/`) + implementation
  plan (private repo `docs/plans/`, per `dev-plan` skill).

## Pitfalls

- **Single model family:** all children inherit the delegation pin, so all
  roles share blind spots (no maker/checker split). DISCLOSE this in the
  delivery; offer to re-run the dissenting roles on a different model to
  stress-test the verdict.
- **AGENTS.md may be blocked** by the html_comment_injection heuristic in
  subagent contexts — don't make the design depend on reading it; provide
  the needed conventions in the brief.
- **Children can't clarify** — if the brief is ambiguous, they guess. Put
  the answers in the brief, not the questions.
- **Prefer return-in-JSON over file writes** for children (governance
  marker gate blocks their writes unpredictably).
- Keep each role's brief concrete (real paths, real examples) — abstract
  briefs produce generic scores that don't discriminate between options.
