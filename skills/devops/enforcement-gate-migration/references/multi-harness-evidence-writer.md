# Writing Evidence for a Gate Across Heterogeneous Harnesses

One gate, N harnesses, each with a DIFFERENT way of doing the thing the gate wants
to see. Depth for step 2-3 of the procedure; read it before writing or fixing any
evidence writer.

## The trap this prevents

A gate is satisfied by EVIDENCE. The evidence is written by a per-harness adapter.
If the adapter keys on the vocabulary of the harness the gate was born in, it is
unreachable in every other one — and unreachable looks exactly like working:

- the hook registers; the guard prints `hook registered: tool_result`
- the adapter's code path is syntactically valid and lints clean
- nothing is EVER recorded, so the gate refuses forever while reporting nothing wrong
- the agent on the other harness (which did everything right) is the one who looks broken

Symptom to recognise: a harness's commits are refused "for no reason", and the
store holds zero rows for that harness — only synthetic test rows.

## Establish the harness's REAL mechanism — drive its own package

Never infer the mechanism from a skill, a doc, a comment, or the other harness's
tool name. Ask the harness itself, using its public entry points:

1. Locate the installed release (a launcher usually names it: read the launcher,
   find the version dir).
2. `grep -r` its whole bundle for the OTHER harness's identifier. Zero matches is
   your proof the old name cannot arrive — not an argument, a measurement.
3. Instantiate its tool factories and PRINT the parameter schema of the tool the
   adapter will have to read (the parameter name is easy to guess wrong).
4. Print the instruction the harness injects into its own system prompt about the
   capability. That text is the harness telling you what it expects the model to do,
   and it is the authoritative statement of the mechanism.

Commit that probe as a `scripts/`-style file under the harness tree and capture its
output to the repo's evidence area. A probe retyped each time is not re-runnable;
the next reader needs one command.

Worked example (Pi, driving `@earendil-works/pi-coding-agent`): the bundle contains
no `skill_view` at all, `createReadToolDefinition(...).parameters` is
`{path, offset, limit}`, and its prompt says *use the read tool to load a skill's
file*. So Pi's load mechanism is a read of `<...>/<skill>/SKILL.md` — nothing like
the `skill_view(name)` tool the gate's own harness uses.

## Record what HAPPENED, not what the other harness would have said

Give the checker a way to accept each real mechanism, and record each under its TRUE
tool name:

| Harness mechanism | Record `tool_name` | Record `content` |
|---|---|---|
| dedicated load tool (`skill_view(name)`) | the tool's own name | the tool's own input |
| read of the capability's file | `read` | the read's own input (`{path, ...}`) |

Do NOT launder one into the other. Writing a `skill_view` row for a read makes the
store assert something that never happened, and the store is evidence — an auditor
or a later gate reads it as fact. Add a predicate per mechanism instead.

Only gate-relevant calls are recorded. A writer that stores every tool call turns
evidence into a transcript.

## The checker's predicates

Each mechanism needs its own predicate, OR'd, matched PRECISELY:

- **Match the capability's OWN location, not a bare name.** A read branch that matches
  `SKILL.md` anywhere lets a read of an unrelated file satisfy the question, and the
  gate's answer is a PERMISSION — an over-match reports work that was never done.
- **Never require a value to sit at a fixed POSITION in stored JSON text.** Matching
  `%/name.md"` looks right against the one shape you have in hand and fails the moment
  the payload carries a second key (`{"path": ..., "name": ...}`) or the writer stores
  the tool's real input (`{"path": ..., "limit": ...}`). Anchor on the full segment and
  leave the tail open; keep a widening `%` on both sides of the discriminating part.
- **Escape LIKE metacharacters in the interpolated VALUE, never the pattern.**
  `%` and `_` are wildcards in the value position too, so a name containing `_`
  over-matches; but escaping the WHOLE pattern escapes your own intentional `%` and
  turns the predicate into a literal match that can never succeed (both predicates go
  silently to zero). Escape backslash first, then `%`, then `_`, on the value only,
  and SQL-quote the assembled pattern afterwards.
- **Keep the session scope in every branch.** A predicate that drops `session_key` for
  one mechanism stops being session-scoped for that mechanism.

Test the predicate by capturing the SQL the real builder emits and asserting the
DISCRIMINATING parts (the own-directory match, the escaping, the session scope) —
whitespace-tolerantly, since the SQL is composed across f-string lines. Then exercise
it end-to-end against the real store.

## Identity: ask, never derive

The gate asks about a specific identity (usually the active lock's session id). The
writer must be handed that SAME id. Two ways to get it wrong:

- deriving it locally from an env var or a state file — a second derivation of "which
  session is this", which drifts from the gate's;
- requiring the lock to exist first — but capabilities are often loaded BEFORE the
  lock is opened, so the common timing case writes nothing.

Expose a READ-ONLY verb over the same implementation the gate uses and have the adapter
ASK for it. Resolve it as: the covering lock's id when one exists, else this caller's
own per-repo id — which is the value the lock will carry a moment later, so both
timings converge. Where several locks cover one repo, mirror the gate's own preference
(an interactive lock outranks an unattended one) and report every covering id, or the
two sides pick differently exactly when it matters.

## Verify the guard DISCRIMINATES

A guard that has never failed on the broken revision proves nothing. Give the guard an
env seam pointing at the file under test, extract the PRE-FIX revision from git, and
run the guard against it — it MUST fail, and on the case that names the defect. Assert
the extraction is genuinely pre-change (the new symbol is absent) so a baseline that
silently resolves to the fixed code cannot pass quietly.

## Fixture cleanup in a shared store

A test that writes to the real store must delete its own fixture and ASSERT it is gone.
The write role often cannot DELETE even though it can INSERT — try the admin role the
schema ships, then the write role, and fail loudly naming the retained key if neither
can clean up. Leaving rows behind in a fleet-wide store is not a neutral outcome.
