---
name: career-document-writing
version: 1.0.0
description: "Use when writing the user's resume or LinkedIn profile."
platforms: [linux, macos]
metadata:
  hermes:
    tags: [writing, resume, linkedin, positioning, career, documents]
---

# Career & Profile Documents

Triggers: resume/CV, LinkedIn profile (headline, About, experience, skills,
Featured, Open-to-Work, Providing Services), cover letter, professional bio, job
description, or "position me for X roles / attract Y opportunities".

## Procedure

1. **Survey the corpus before writing a word.** The user's career source
   material is already on disk — a resume, a target job description, a current-
   responsibilities doc/builder, and a market survey of English-language AI
   roles in his city. `search_files` for the name/brand, then `read_file` the
   hits. They carry the metrics, client names, dates, employers, and education.
   Asking the user for facts already on disk wastes his time and signals you
   did not look.
2. **Audit the brief against the evidence base and put the audit FIRST.** For
   every claim a brief asserts, confirm it appears in a source file, and deliver
   the mismatches as PART A before PART B — the user asks for "improvements and
   gaps" and expects that review inside the same delivery, not as a second
   request. Number the items; each is gap → why it matters → the fix.
3. **Never copy an unconfirmed claim into the copy.** A client name, job title,
   metric, or certification with no source gets flagged (name the file it is
   absent from) and either omitted or left as a bracketed slot. Publishing an
   unsupported brand is the one error that costs a real engagement.
4. **Mine the missed assets.** Briefs routinely omit the strongest material that
   is already on file: deal sizes, pipeline totals, growth percentages, POC
   counts, named enterprise clients, employer pedigree, education. A technology
   list is the weakest content in a profile; documented outcomes are the
   strongest. Lead with proof, not with a self-description.
5. **Bracket every unknown and list the open questions at the end** —
   `[Company]`, `[Start Year]`, `[email]` — so one reply from the user closes the
   whole document instead of another cycle of edits.
6. **State experience levels honestly and explicitly** — "senior in X and Y;
   hands-on at mid-senior level in Z". For consulting/advisory targets add the
   anti-mis-bucketing line ("not seeking a junior or entry-level developer
   position"); otherwise screening buckets a multi-decade veteran as a mid-level
   dev. Label legacy stacks as prior experience so they are not read as current
   depth.
7. **Deliver in two parts in chat, then persist.** PART A gaps/improvements;
   PART B the paste-ready copy, section by section under the platform's own
   labels. Save the whole package as `.md` in the career-corpus directory and
   print its absolute path — the CLI has no attachment channel.
8. **Governance and cost.** The file write is gated: `begin_change` first, then
   score with real numbers (a note alone is refused), then `end_change`. Compose
   once and write once (large content is the expensive part); verify with a
   section grep against the saved file rather than re-reading it.

## Tone & format (user preference)

- Professional, confident, credible — never overstated or inflated. Senior and
  consultative, not corporate-generic.
- Banned filler: "results-driven", "visionary", "passionate professional",
  "technology enthusiast", "dynamic", "leverage", "synergy". Specific and
  credible language only.
- First person for About/bio sections; concise enough to stay readable.
- No invented metrics, certifications, titles, employers, or dates — every
  number traces to a source file.
- Contact details stay as `[Email]` / `[Phone]` placeholders in the artifact;
  never paste a real address or number into the document.
- Keep any second specialization (music, creative, domain) integrated as a
  complementary professional thread, tied to the technical work by a real
  mechanism (e.g. attribution/provenance, metadata, rights administration) —
  never as an "also interested in" aside.
- When the user asks to add an ethics thread, anchor it in practice he actually
  performs (auditability, human review, consent/provenance, disclosure of AI in
  the loop) and never dress it as a certification or compliance badge he does
  not hold.

## Platform depth

`references/linkedin-profile-package.md` — the full LinkedIn deliverable
checklist, character limits, headline structure rules, and the skills /
Featured / Services / Open-to-Work conventions.
