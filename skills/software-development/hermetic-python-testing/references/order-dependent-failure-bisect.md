# Bisecting an order-dependent test failure

A test that passes alone and fails in the full run is polluted by something that
ran earlier in the same process. Do not read the suite hunting for it — the
search is mechanical and cheap.

## Confirm the class before hunting

```bash
python3 -m pytest tests/test_the_victim.py -q -p no:cacheprovider   # expect: passes
```

Run the victim alone THREE times before believing it is order-dependent at all —
identical code that fails some runs and not others is a race or an environment
effect, and if it fails alone the cause is in that test, not in a neighbour.

## Pair the victim with each candidate

The population is small: the files that touch the module the victim reads.

```bash
for f in $(grep -rl '<module-under-test>' tests/ --include='*.py'); do
  printf '%-60s ' "$f"
  python3 -m pytest "$f" tests/test_the_victim.py -q -p no:cacheprovider | tail -1
done
```

The first pair that fails identifies the polluter directly. It is usually exactly
one file, and usually not the one you suspected. Paste the pairing table into the
closing note — it shows the search rather than asserting its conclusion.

## If BOTH halves fail, the split is wrong

If running each half of the suite with the victim gives two failures, the
polluter is not file-specific: suspect the runner's ENVIRONMENT — PATH, HOME, an
inherited variable, a leaked `sys.modules` entry — rather than a neighbouring
test. Re-run the victim alone; if it now fails alone too, you are inside a time
window, not an ordering effect.

## When the failure will not reproduce

Do not report your fix as "the cause". Do this instead:

1. **Write a control that reproduces the MECHANISM deterministically.** If the
   suspicion is "an inherited value satisfied this case", inject that value and
   drive the code directly — e.g. put a stub executable on PATH and run the tool;
   if the tool then reports the healthy verdict it should only give a complete
   host, the mechanism is proven regardless of which run first exposed it.
2. **Fix the probe so the mechanism cannot apply** — scrub the binary's
   directories out of PATH, delete the ambient variable, point the env file at a
   path that does not exist.
3. **Say plainly that the specific polluter was never identified.** "Mechanism
   proven, culprit unidentified" is an honest and accepted report; "fixed the
   cause" when you only removed one proven route to the failure is not. Make the
   failure message name the route it took (`pi_on_PATH=…`, `token_resolved=…`) so
   the next occurrence diagnoses itself.

## Probing for an environment leaker

For an `os.environ` leak, a throwaway pytest plugin is cheaper than bisecting: a
module on `PYTHONPATH` with one `pytest_runtest_setup` hook that prints when the
leaked variable is present, plus the current test id. Run it with `-s` — without
that, pytest discards a passing test's output and the probe looks silent. Check
at SETUP, not teardown: fixtures undo their own patches during teardown, so a
teardown probe misses real leaks.
