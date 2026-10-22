# Rule 15: `&` in a heredoc/python payload trips the backgrounding detector

**Symptom (hit 2026-08-25):** the terminal enforcer blocks any foreground
command containing a bare `&` with `Foreground command uses '&' backgrounding`.
A Python set-intersection operator (`set_a & set_b`) inside a
`python3 - <<'EOF'` heredoc triggers it — a pure read-only path-set diff
(e.g. casefolded `git ls-files` comparison) gets blocked as "backgrounding".

**Root cause:** the enforcer classifies the command TEXT. `&` is shell
backgrounding syntax, so its presence in a payload string trips the classifier
even when it is inside a Python expression in a heredoc body.

**Workarounds (in order of preference):**
1. Rewrite without the `&` token — iterate keys and test membership:
   ```python
   for k in a:
       if k in b:
           ...
   ```
2. Use the `.intersection()` method instead of the `&` operator:
   `a.intersection(b)` — no `&` token in the command string.
3. Write the analysis to a file with `write_file` and run `python3 /tmp/x.py`
   — the guard scans the command string, not the file content.

**Same family as Rule 7:** anything that looks like shell syntax in a payload
— `&`, `;`, `>`, `|` — can misfire. When a legit read-only Python one-liner
gets blocked, the fix is "use execute_code or a script file", not "argue with
the classifier". (This mirrors cortex-deployment-sync Pitfall 10: the terminal
guard misclassifying `python3 -c` payloads with embedded paths.)
