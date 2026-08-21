<!-- Hermes fleet efficiency block (additive — safe to ignore, safe to remove) -->
<!-- Managed by apply-repo-efficiency.sh; re-running never duplicates. -->

## Session Efficiency (Hermes fleet — additive guidance)

These are cost/throughput principles for AI coding agents working in this
repo. They change nothing about the repo's own rules; they only tell the
agent how to spend its own tokens efficiently.

- **Batch independent tool calls** in one turn; prefer fewer, larger
  operations over many tiny round-trips. Each call re-sends context —
  cache-hit, but still billed; output tokens are the real cost.
- **Don't re-derive established facts** — reference prior conclusions in one
  clause and advance. Re-reading files to re-learn what a prior turn already
  established burns tokens.
- **Keep the session alive for related work** — continuing one session beats
  starting fresh (history re-sends are cache hits; a new session pays a cold
  system-prompt start and re-explains context).
- **Compact responses** — deliver the answer, not the process. No status
  narration, no "let me" preambles.
- **Thinking economy** — match reasoning depth to task difficulty; don't
  over-deliberate simple lookups or mechanical edits.
- **Ask once, act twice** — prefer acting on an obvious default over
  clarifying questions that only burn a round-trip.
