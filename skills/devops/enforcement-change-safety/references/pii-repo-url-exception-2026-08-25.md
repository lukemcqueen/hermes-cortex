# PII Gate Repo-URL Exception — Design & Verification (2026-08-25)

## Problem
The enforcer PII gate blocked writes containing the owner segment of this
repo's own public GitHub URL because the handle embeds the blocklisted
surname. The repo is public — its URL is the sanctioned address and
README/docs must link it.

## Design
- `_OWNER_HANDLE = "luke" + <surname>` — built at runtime, never the literal
  in source (the gate blocks its own term).
- `_PII_REPO_URL_RE` covers: https github.com, raw.githubusercontent.com,
  img.shields.io/github/license (badge), and `git@github.com:` ssh forms.
- Allowance check in `_check_pii_content_gate`: context window
  `ctx_start = m.start() - 60`, end `m.end() + 40` — the badge form has
  ~38 chars of URL prefix before the owner segment; a ±12/8 window misses
  it and the allow fails closed.
- Terminator `(?=/|$|\s|[),.;])` — markdown links close with `)` after the
  repo path; without it the badge form never matches.

## RED-GREEN matrix (9 cases, all pass)
ALLOWED (5): https clone, https .git, raw URL, ssh URL, badge URL.
BLOCKED (4): surname in prose, prose + repo URL in same doc, OTHER repo
under same owner, non-repo private URL.

## Bootstrap problem
The enforcer file itself contains blocklisted terms, so patch/write_file
cannot edit it — the gate blocks its own source. Sanctioned path: write a
fixer script to /tmp (outside shared surface), run via terminal, ast.parse
before write-back. Same as creation commit 7dbe7335.

## Heredoc escaping trap
Regexes with `\"` or `\\` inside `python3 - <<'EOF'` heredocs get mangled
(raw-string char classes with quotes break parsing; anchor asserts fail).
Write the fixer to a file instead; ast.parse before write.

## Deploy ≠ in-memory (plugin variant)
Enforcer hooks load at gateway start. Deploying the fixed file
(cortex-update.sh / dogfood) updates disk; the RUNNING gateway keeps the
old gate until restart — same-session write-tool calls still see old
behavior. Commit-time git hooks read the deployed file, so they reflect the
fix immediately. Verify with importlib on the DEPLOYED path, not just the
repo copy.

## Tests
tests/test_enforcer_pii_gate.py: 16 pass (2 new repo-URL allowed cases).
