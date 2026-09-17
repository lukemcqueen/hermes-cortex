# Consulting DeepSeek Pro via OpenRouter (design-research pattern)

Use when a design question benefits from an outside expert model opinion (e.g. interface review, architecture sanity check) before writing the design doc.

## Recipe
1. Key lives in `~/.hermes/.env` as `OPENROUTER_API_KEY` — read it in a subshell, never print:
   ```bash
   KEY=$(grep '^OPENROUTER_API_KEY=' ~/.hermes/.env | cut -d= -f2- | tr -d '"')
   ```
2. Write the request body to a JSON file (heredoc-quoted, no curl|pipe-to-python):
   ```bash
   cat > /tmp/q.json <<'EOF'
   {"model": "deepseek/deepseek-v4-pro", "messages": [{"role": "user", "content": "<the concrete design question>"}], "max_tokens": 3000}
   EOF
   ```
3. POST and parse from file, not pipe:
   ```bash
   curl -s https://openrouter.ai/api/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer $KEY" -d @/tmp/q.json -o /tmp/ans.json
   python3 -c 'import json; print(json.load(open("/tmp/ans.json"))["choices"][0]["message"]["content"])'
   ```

## Pitfalls
- **deepseek-v4-pro is a REASONING model — budget max_tokens ≥ 3000.** With a small cap (e.g. 900) every token goes to `reasoning` and `content` comes back EMPTY/None while the call still bills. If content is empty, check `usage.completion_tokens_details.reasoning_tokens` before concluding the model failed.
- **The answer arrives in `message.content`; the reasoning trace is `message.reasoning`.** Never cite the reasoning trace as the finding.
- **curl | python3 trips the security scan** (pipe-to-interpreter). Write to a file first — also makes the raw response inspectable.
- Cost is visible in `usage.cost` (~$0.005 for a 900-token answer); one focused question per call, not chit-chat.
- `web_extract` may be unavailable depending on search backend — fetch pages with Python `urllib` + regex tag-strip instead of guessing the tool works.

## Use of the output
Treat it as EXPERT INPUT to the design, not the design: overlap-check against settled concepts, keep what survives, ground the final doc in primary sources. The design doc cites sources, never 'DeepSeek said'.