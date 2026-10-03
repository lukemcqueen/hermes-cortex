# Gateway `/new` — acceptance evidence (ARCHIVE semantics)

Regenerate with: `bash ops/scripts/cortex_gateway/run-new-command-evidence.sh`

Drives the DEPLOYED gateway against the REAL `pi` binary. A probe chat id is
used throughout — never a real one, since this file is committed.

| # | Criterion | Result |
|---|---|---|
| 1 | Session id before `/new` | `hc-pi-evidence-probe-895b72fb` (unsuffixed: an existing conversation never moves) |
| 2 | That session really holds a memory | seeded `ORCHID`, recalled `ORCHID` |
| 3 | `/new` is handled by the gateway (not answered as a prompt) | `🆕 New session (generation 1). Previous conversation archived as `hc-pi-evidence-probe-895b72fb`. Your next message starts fresh.` |
| 4 | The next session id DIFFERS | `hc-pi-evidence-probe-895b72fb-g1` |
| 5 | The new session has NO memory of it | agent replied `I don't have a codeword for you. Nothing by that name exists in your project files, environment variables, or my current context.` |
| 6 | The OLD transcript is still on disk (ARCHIVE) | `2026-10-03T14-12-10-466Z_hc-pi-evidence-probe-895b72fb.jsonl`, 56850 bytes |
| 7 | The generation PERSISTED | reopened book reports generation 1 |

## Artefacts on disk

- `2026-10-03T14-12-10-466Z_hc-pi-evidence-probe-895b72fb.jsonl` — 56850 bytes
- `2026-10-03T14-12-19-335Z_hc-pi-evidence-probe-895b72fb-g1.jsonl` — 61322 bytes
- `2026-10-03T14-12-19-335Z_hc-pi-evidence-probe-895b72fb-g1.jsonl` — 61322 bytes

**Verdict: PASS** — the rotation is real (memory gone), the archive is real (transcript kept), and the generation survives a reload.
