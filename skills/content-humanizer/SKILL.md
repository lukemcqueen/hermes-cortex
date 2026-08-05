---
name: content-humanizer
version: 1.0.0
description: "Makes AI-generated content sound genuinely human — not just cleaned up, but alive. Use when content feels robotic, uses too many AI clichés, lacks personality, or reads like it was written by committee. Triggers: 'this sounds like AI', 'make it more human', 'add personality', 'it feels generic', 'sounds robotic', 'fix AI writing', 'inject our voice'. NOT for initial content creation (use content-production). NOT for SEO optimization (use content-production Mode 3)."
triggers:
  - "humanize content"
  - "make content sound human"
  - "remove ai voice"
---

## When to Use

Use when text reads like a language model wrote it: robotic rhythm, AI clichés, zero personality, "written by committee" voice. Triggers: "this sounds like AI", "make it more human", "add personality", "sounds robotic", "fix AI writing". This skill edits existing text — for first drafts use content-production; for SEO-only fixes use that skill's SEO pass.

## Workflow

1. **Read it aloud, cold.** Mark anything you'd never say in conversation — those marks are your edit list.

2. **Kill the AI cliché list.** Replace or delete every instance of: "delve", "landscape", "it's important to note", "in today's fast-paced world", "elevate", "unlock", "moreover", "furthermore", "in conclusion", "seamless", "robust", "leverage", "game-changer", "navigate", "in the realm of", "dive into", "ever-evolving", "cutting-edge", "empower". Replace with what it means, or cut — most are filler.

3. **Vary sentence rhythm.** Alternate short, medium, and long sentences — at least one under 8 words per paragraph. Break any stretch where three sentences in a row share the same length and shape.

4. **Add specificity.** Every vague claim gets a concrete anchor: a number, name, date, price, or real example. Swap "many teams struggle with" for "three agencies fumbled this in Q2". No fact? Flag it — never invent it.

5. **Apply voice mechanics:**
   - Contractions: "it's", "don't", "we've" — un-contracted prose reads stiff.
   - Active voice: "the API returns an error", not "an error is returned".
   - First person: "we found" beats "one might find".
   - Punchy openings: "Content is dead." beats "In today's fast-paced landscape…".

6. **Re-read aloud** — any sentence that trips you gets rewritten. Human prose should be speakable in one breath.

### Before / After Example

**Before (AI-tells bolded):** "In today's fast-paced digital landscape, it's important to note that content marketing has evolved significantly. By leveraging the power of strategic storytelling, brands can elevate their engagement metrics and unlock new growth opportunities. Moreover, consistency remains a crucial component in this ever-evolving realm."

**After:** "Content marketing changed while we weren't looking. In 2018, a 2,000-word post could carry a quarter of our traffic. Now the same post earns maybe a hundred visits — unless it says something nobody else does. We tested this for six months on three brands. Storytelling helps. Consistency helps more. But neither works if the post won't take a position."

### The 10 AI-Tells Checklist

Scan the edited text for each; any hit means another pass:

1. "delve", "landscape", "elevate", "unlock", or "leverage"
2. "It's important to note" / "It's worth noting" / "It's crucial to"
3. "In today's fast-paced world" / "in the digital age"
4. Three or more same-length sentences in a row
5. Zero contractions outside legal docs
6. A body paragraph with no numbers, names, dates, or concrete examples
7. Passive voice where the actor is obvious ("was decided" vs "we decided")
8. Hedge pile-ups: "somewhat", "arguably", "generally speaking"
9. Paragraphs opening with "Moreover", "Furthermore", "Additionally", or "However"
10. An opening that takes more than one sentence to say anything

## Pitfalls

- Editing only vocabulary: deleting "delve" while keeping the robotic rhythm just swaps one tell for another.
- Over-correcting into slang or forced casualness — human ≠ unprofessional.
- Inventing specifics to fill gaps: a fake stat is worse than an honest "we don't have the number".
- Rewriting in the wrong voice: ask whose voice you're writing in (founder, agency, corporate) first.
- Running one pass and stopping — the 10-tells checklist is the mandatory second pass.

## Verification

- Run the 10-AI-tells checklist and report any that still fire.
- Read the final text aloud: does any sentence trip the tongue?
- Diff against the original: meaning survives every edit? (Specifics added, claims unchanged.)
- With a voice reference (past posts, brand guide), it should sit naturally next to them.
