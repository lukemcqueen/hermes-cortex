# Rule 33 — All-Repos Discipline Gates & the Session Split

## A discipline gate must fire where the agent it governs actually works

A gate meant to change an agent's behaviour (survey-before-build, plan review,
any ritual discipline) is placed by WHERE that agent commits, not by where an
existing gate happens to live. A reflexion gate wired only into the cortex repo
governs NONE of a dev agent's work in project repos — the exact failure that made
Titus-style agents build without surveying. The fix reused the EXISTING generic
skill-checker (`hc-reflexion-check.py --skill <name>`) in a loop over the ritual
skills (`reflexion-check survey-before-action prove-before-create agent-contract`)
rather than writing a new verifier: loading = reading the SKILL.md, recorded as a
tool event, so the gate refuses a commit until each ritual skill's content was
loaded that session.

## The session-presence split: govern every repo WITHOUT blocking humans

Host-wide gates must split on whether a governed session exists — the same signal
the reflexion gate already carries:

- a governed agent's commit holds a begin_change lock and has recorded tool events
  → an ACTIVE session exists → the gate applies and refuses on missing evidence;
- a human `git commit` by hand holds no lock → no session resolvable → skip (exit 0),
  via a `--skip-no-session` verifier flag.

Missing that split is both failure modes at once: cortex-only placement misses the
agent the gate was meant to change, and an unscoped host-wide version blocks manual
commits. When a negative-case test cannot manufacture a governed session, stub the
checker (python stub asserting the `--skip-no-session` flag is forwarded) so the
skip path and the refuse path are pinned separately.

## A repeated violation = a gate problem, not a documentation problem

If an agent keeps building without surveying or testing, the rule was prose (skill
body, AGENTS.md bullet) and the agent never loaded it. Enforce the discipline at
commit time via the generic skill-checker loop and the write gate (lock-only is
not enough); put aircraft rules where the agent always reads them (AGENTS.md) AND
make them bind (ritual-gate loop).

## Block messages must name the LIVE tool prefix

A gate's block message that NAMES a tool must name the prefix the registered MCP
server actually serves. When an MCP server is RENAMED (e.g. `loop_governance` →
`review`), every block message, skill, and doc still quoting the old
(`mcp__loop_governance__*` vs the live `mcp__review__*`) makes a healthy system
read as "governance broken" to every agent that copies the documented name and
finds no tool. The enforcer may accept both prefixes in its session-injection
while the tool surface answers only one — sweep block messages + skills + docs
TOGETHER with the rename, and keep each documented tool name pointing at the
registration that actually serves it.
Related: pi-coding-agent "commit-time ritual gate" section.
