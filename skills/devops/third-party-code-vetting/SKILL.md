---
name: third-party-code-vetting
version: 1.0.0
description: "Vet third-party code before it enters the repo or runs on a host — upstream patches, vendored scripts, installer snippets, peer-submitted cron scripts. Use when integrating external code of any kind."
triggers:
  - "vet third-party code"
  - "external code review"
  - "vendored script"
  - "upstream patch"
---

# Third-Party Code Vetting

Vet external code before it enters the repo or runs on a host: upstream
patches, vendored scripts, installer snippets, cron scripts from peers,
MCP server code. The bar is provenance + behavior, not a glance at the diff.

## Checklist

1. **Source integrity** — where did it come from? Commit hash, signed
   release, PR number, or named peer. Reject code with no provenance.
2. **Read the whole file** — never vet from a diff summary or a
   description. A 200-line upstream patch shipped on an unexamined premise
   is the classic failure (2026-08-03).
3. **Static scan** — `adversarial-verify.py --file <script> --level A4
   --gate` on any scripts; `secret-leak-detector.sh` for PII/creds.
4. **Behavior check** — run it with boundary inputs in a sandbox: tmp
   workdir, no network, no sudo. Attack the implicit assumptions
   (Technique F), don't just execute the happy path.
5. **Dependency check** — stdlib-only unless declared; no silent network
   calls; no writes outside the declared scope.
6. **Persistence check** — what does it install or change? (crons,
   systemd units, config files, auto-start hooks). Reject silent
   persistence; require explicit opt-in.
7. **License** — compatible with the target repo (MIT for hermes-cortex).

## Decision

| Finding | Decision |
|---------|----------|
| No provenance | REJECT |
| Injection / exfiltration / hidden persistence | REJECT |
| Unaudited runtime network access | REJECT or fix + WARN |
| Provenance + clean scan + sandbox pass | APPROVE |
| Minor issues (paths, PII, naming) | APPROVE after fix, note it |

## Verify after approval

- Commit with `-F` message citing the source (hash/PR/author)
- Deploy and run the real invocation (doctor Script run evidence)
- Never `--no-verify` to ship a vet-rejected change
