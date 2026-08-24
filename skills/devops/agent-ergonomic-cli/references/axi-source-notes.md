# AXI Source Notes — Benchmarks, Catalog, Adoption Rules

Condensed external knowledge from the AXI project (Kun Chen, MIT), fetched
2026-08-24. See SKILL.md for the 10-principle cheat sheet.

## Published benchmark evidence (Claude Sonnet 4.6, 915 runs)

### GitHub (425 runs, 17 tasks × 5 conditions × 5 repeats)

| Condition | Success | Avg Cost | Avg Duration | Avg Turns |
|---|---|---|---|---|
| gh-axi | 100% | $0.050 | 15.7s | 3 |
| gh (CLI) | 86% | $0.054 | 17.4s | 3 |
| GitHub MCP | 87% | $0.148 | 34.2s | 6 |
| GitHub MCP + ToolSearch | 82% | $0.147 | 41.1s | 8 |
| MCP + Code Mode | 84% | $0.101 | 43.4s | 7 |

### Browser (490 runs, 14 tasks × 7 conditions × 5 repeats)

| Condition | Success | Avg Cost | Avg Duration | Avg Turns |
|---|---|---|---|---|
| chrome-devtools-axi | 100% | $0.074 | 21.5s | 4.5 |
| dev-browser | 99% | $0.078 | 28.6s | 4.9 |
| agent-browser | 99% | $0.088 | 24.6s | 4.8 |
| chrome-devtools-mcp-compressed | 100% | $0.091 | 29.7s | 7.6 |
| chrome-devtools-mcp-search | 99% | $0.096 | 29.4s | 7.5 |
| chrome-devtools-mcp | 99% | $0.101 | 26.0s | 6.2 |
| chrome-devtools-mcp-code | 100% | $0.120 | 36.2s | 6.4 |

Read: AXI ≈ 100% success at lowest cost; MCP costs ~2× in dollars AND turns.
Turns are LLM calls — fewer turns is the cost lever.

## TOON (Token-Oriented Object Notation)

~40% token savings vs equivalent JSON; readable by agents. Spec at the AXI
repo (toonformat.dev). Syntax: `name[N]{field,list}:` header, then CSV-style
rows; `count:` aggregates; `help[N]:` suggestion blocks; errors as
`error:`/`help:` pairs. Convert at the output boundary — internal logic
stays JSON.

## Reference implementations (study these)

Official: gh-axi (GitHub), chrome-devtools-axi (browser), lavish-axi (human
review of HTML artifacts), quota-axi (usage windows, data-only local-first).

Community: jj-axi (jujutsu VCS), pg-axi / sqlite-axi / mongodb-axi / redis-axi
(DBs), docker-axi / kubernetes-axi, slack-axi / gws-axi, notion-axi,
obsidian-axi (filesystem, atomic writes, no server), mssql-axi (mutations
double-gated with dry-run default), cyber-mux (tmux/herdr/WezTerm).

All in github.com/kunchenguid/axi (catalog generated from catalog.yaml).

## Adoption rules of thumb (from the 2026-08-24 Cortex distillation)

- Machine protocol stays JSON; TOON is output-boundary only.
- Agent-facing CLI stdout: TOON preferred for new scripts; retrofit
  high-frequency tools incrementally (hc, doctor).
- Cron deliveries keep cron-format-standard (already AXI-aligned); add
  totals/truncation hints when evidence runs long.
- Human chat output unchanged.

## Notable spec details

- Default list limits high enough for one-call coverage (most repos <100
  labels → default 100, not 30).
- Truncation limit 500–1500 chars; suggest `--full` only when truncated.
- Aggregates only if the backend can compute them cheaply — a summary, not
  the full data.
- Setup/session-hook commands: explicit opt-in, idempotent, PATH-verified
  binary name, path repair after reinstall, directory-scoped.
- Skills secondary to hooks: static (strip live state), trigger-shaped
  frontmatter, non-interactive command examples (npx -y), single source of
  truth with a --check CI step so the skill never drifts.
- --version fast path: keep VERSION in a leaf module (builtins only),
  defer heavy CLI graph to dynamic import; test against `node -e
  "console.log(1)"` floor, not absolute ms budgets.
