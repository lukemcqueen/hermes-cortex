# "Governance MCP is broken" Is Usually a Name-Prefix Mismatch

An agent (or a doc reader) reporting that the governance/review MCP tool is "missing" /
"broken" / "tool not found" is almost always a NAME-PREFIX MISMATCH: the docs, the enforcer
block messages and the skill files say `mcp__loop_governance__*` while the server is
registered under a different name (`review` — tools are `mcp__review__*`), so copying the
documented prefix calls a nonexistent tool and the agent concludes the whole server is down.

## Diagnose BEFORE touching the binary

1. Read the LIVE registration: `hermes mcp list`. Note the registered server NAME.
2. Compare the tool prefix that name yields (`mcp__<name>__*`) against the prefix every doc and
   every enforcer block message tells agents to call.
3. The mismatch is usually the WHOLE story. Fix the DOCUMENTS AND MESSAGES (or, when two roles
   are genuinely wanted, deploy a role-gated single binary).

Never "revert" or "repair" a healthy server because a reader followed a stale name. A doctor
showing 0 FAILs plus the review MCP answering a call is proof the server is fine; the break is
in the naming contract the fleet reads, and the reader's reality — not the code — is what
"broken" means to the fleet.

## When the two names ARE meant to be two role-distinct roles of ONE binary

A single shared binary registered under two names (review-only tools vs lock-lifecycle tools)
must be role-gated to be safe. The mechanism that keeps it zero-regression and testable:

- Role env read at CALL time, not module load — `os.environ.get("CORTEX_MCP_ROLE", "")` inside
the predicate, so ONE import is testable across roles.
- `list_tools` is a thin wrapper that filters the full list by the predicate (the giant
tool-literal stays a private `_list_all_tools`; do not refactor it).
- `call_tool` refuses out-of-role tools by name WITHOUT dispatching.
- no/unknown role = the full set (fail-open), so an existing single no-env registration is
unchanged: zero regression until a role env is deployed.
- Partition spec (which tool belongs to which role) lives ONCE in the binary's constant; the
test imports `set(mod.REVIEW_TOOLS)` rather than hand-copying it (a second list drifts).

## Coupled rollout: an expectation that starts REQUIRING a new state must land with its producer

When you harden an enforcement/doctor check to REQUIRE a new registration, file, or state
("expect exactly two role-distinct MCP servers" where today there is one), the check and the
deploy that produces that state must ship as a coupled pair. Land the CHECK alone and every
host that has not yet received the accompanying installer/config change FAILS the doctor (or
blocks pushes) until it deploys — a self-inflicted fleet-wide break invisible in the repo diff.

Safe sequence:
1. The binary/mechanism that makes the new state valid is backwards-compatible — it lands as
   its own testable, deployable increment (the mechanism alone is a valid, safe, shippable
   slice; do NOT hold it hostage to the rollout).
2. The new EXPECTATION plus the registration/deploy that satisfies it land together in ONE
   commit, verified by deploying BOTH and re-running the doctor on a live host before push.

The sqlite-concurrency fear behind "two processes, one lock store" is answerable by
measurement before it blocks a design: check `PRAGMA journal_mode` and `PRAGMA busy_timeout` on
the shared DB. `wal` + a non-zero busy timeout means short ledger writes from two processes
serialize cleanly — the concern evaporates instead of costing a redesign.
