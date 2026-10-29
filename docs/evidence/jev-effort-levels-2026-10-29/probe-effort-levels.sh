#!/usr/bin/env bash
# Measure reasoning_effort support and its OUTPUT-token cost, per pool model.
#
# WHY: the effort ladder cannot be guessed. An unsupported level either 400s a turn or is
# silently ignored, and the whole point of the ladder is the thinking-token bill. So before
# any level is written into config/jev-router-models.json, every model the pools can route
# to is asked the SAME mechanical question at each level, and the reply's usage block is
# recorded: accepted (HTTP 200) and how many output tokens it bought.
#
# Input set: the ROUTED models of config/jev-router-models.json, plus the host baseline and
# the priced candidates. One variable changes between rows: the level.
#
# Re-run:  bash docs/evidence/jev-effort-levels-2026-10-29/probe-effort-levels.sh
# Writes:  effort-levels.txt (this run, the committed transcript) and effort-levels.json (raw rows)
# Key:     OPENROUTER_API_KEY, resolved the way the repo resolves it (~/.hermes/.env).
#          Never printed; only presence is reported.
set -u
export LC_ALL=C

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || echo "$HOME/hermes-cortex")"
OUT="$HERE/effort-levels.txt"
RAW="$HERE/effort-levels.json"
LIST="$REPO/config/jev-router-models.json"

norm() { sed -e "s#$HOME#~#g" -e 's/[A-Za-z0-9._%+-]\+@[A-Za-z0-9.-]\+\.[A-Za-z]\{2,\}/<email-redacted>/g' \
             -e 's/\x1b\[[0-9;]*m//g'; }
say() { printf '%s\n' "$*" | norm; }

exec >"$OUT" 2>&1
say "reasoning_effort support and output-token cost, per pool model"
say "generated-by: docs/evidence/jev-effort-levels-2026-10-29/probe-effort-levels.sh"
say "captured-at: $(git -C "$REPO" rev-parse --short=12 HEAD 2>/dev/null || echo '(no git)')"
say "             (captured-at is the revision the working tree sat on when this ran; writing"
say "              this file changes the revision, so no 'tip' line is claimed here)"
say "list:        ${LIST/#$HOME/~}"
say "method:      one fixed mechanical prompt per (model, level); usage.completion_tokens and"
say "             usage.completion_tokens_details.reasoning_tokens are recorded per reply."
say ""

python3 - "$LIST" "$RAW" <<'PY'
import json, os, pathlib, sys, urllib.error, urllib.request

list_path, raw_path = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])


def key() -> str:
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    env_file = pathlib.Path.home() / ".hermes" / ".env"
    for line in env_file.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "OPENROUTER_API_KEY":
            return value.strip().strip('"').strip("'")
    raise SystemExit("COULD NOT VERIFY: no OPENROUTER_API_KEY in the environment or in ~/.hermes/.env")


doc = json.loads(list_path.read_text())
models = []
for tier, specs in (doc.get("tiers") or {}).items():
    for spec, ordered in specs.items():
        for m in ordered:
            if m not in models:
                models.append(m)
for extra in [doc.get("baseline")] + list(doc.get("candidates") or {}):
    if extra and extra not in models:
        models.append(extra)
LEVELS = ["(baseline, no effort field)", "none", "low", "medium", "high"]
BASELINE = "(baseline, no effort field)"

# A mechanical verification turn: the class the bill is dominated by. No design decision in
# it, one small deterministic answer. Identical text at every level, so the level is the
# only variable between rows.
PROMPT = ("Count how many entries below have status pending, and reply with the number only.\n"
          "a=b done; b=c pending; c=d pending; d=e done; e=f pending")

rows = []
for model in models:
    provider, _, bare = model.partition(":")
    if provider != "openrouter":
        rows.append({"model": model, "level": None, "status": "skipped",
                     "detail": "no probe path for provider %r" % provider})
        print("  %-52s %-7s skipped          (no probe path for provider %r)" % (model, "-", provider))
        continue
    for level in LEVELS:
        body = {"model": bare, "max_tokens": 400, "temperature": 0,
                "messages": [{"role": "user", "content": PROMPT}]}
        if level != BASELINE:
            body["reasoning_effort"] = level
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer %s" % key(), "Content-Type": "application/json"})
        row = {"model": model, "level": level}
        try:
            with urllib.request.urlopen(request, timeout=120) as reply:
                payload = json.loads(reply.read().decode())
            usage = payload.get("usage") or {}
            details = usage.get("completion_tokens_details") or {}
            row.update({"status": "accepted", "http": 200,
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "reasoning_tokens": details.get("reasoning_tokens"),
                        "answer": ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")[:40]})
            print("  %-52s %-7s %-16s out=%s reasoning=%s" % (
                model, level, row["status"], row.get("completion_tokens"), row.get("reasoning_tokens")))
        except urllib.error.HTTPError as error:
            row.update({"status": "refused", "http": error.code,
                        "detail": error.read().decode()[:300]})
            print("  %-52s %-7s %-16s http=%s %s" % (
                model, level, row["status"], error.code, row["detail"][:90]))
        except Exception as error:                       # network, timeout, bad JSON
            row.update({"status": "could-not-verify",
                        "detail": ("%s: %s" % (type(error).__name__, error))[:300]})
            print("  %-52s %-7s %-16s %s" % (model, level, row["status"], row["detail"][:90]))
        rows.append(row)

raw_path.write_text(json.dumps({"prompt": PROMPT, "levels": LEVELS, "rows": rows}, indent=2) + "\n")

print()
accepted = [r for r in rows if r.get("status") == "accepted"]
print("probe verdict: %d accepted row(s) of %d attempted" % (len(accepted), len(rows)))
by_level = {}
for r in accepted:
    by_level.setdefault(r["level"], []).append(r.get("reasoning_tokens") or 0)
for level in LEVELS:
    if level in by_level:
        values = by_level[level]
        print("  level %-7s accepted by %d model(s); reasoning tokens min=%s max=%s mean=%.1f" % (
            level, len(values), min(values), max(values), sum(values) / len(values)))
for r in rows:
    if r.get("status") not in ("accepted", "skipped"):
        print("  NOT ACCEPTED: %s at level %s -> http=%s %s" % (
            r["model"], r["level"], r.get("http"), str(r.get("detail"))[:140]))
print()
print("read this as: a refusal is a RESULT (that model must not be sent that level), not a")
print("broken probe. Accepted levels are what the capability map may declare.")
PY
RC=$?
say ""
say "rc=$RC (0 = the probe ran to completion; refusals above are results, not failures)"
exit $RC
