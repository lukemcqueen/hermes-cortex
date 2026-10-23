# Verifying a Schema Guard on the LIVE Store

The hermetic battery (scratch DB, probe role) proves the MIGRATION is correct. It says
nothing about the HOST: whether the deploy applied it, whether the running server serves
the new body, and whether the guard actually refuses on the real data. Both halves are
required, and the second one has to leave the store untouched.

## The rolled-back live proof

Drive the forbidden arc AS the non-privileged role, inside a transaction you roll back.

```bash
OUT=$(docker exec -i mycortex-postgres psql -U "mycortex_reader_<orch>" -d <live_db> \
      -v ON_ERROR_STOP=1 <<'SQL' 2>&1
BEGIN;
-- any GRANT the probe needs goes INSIDE the txn: it disappears with the rollback,
-- and it keeps the refusal you observe attributable to the GUARD, not to a grant.
SET LOCAL SESSION AUTHORIZATION mycortex_reader_probe;
UPDATE <schema>.<table> SET status='completed' WHERE id='<fixture>';   -- expect refusal
ROLLBACK;
SQL
) || RC=$?
```

- **`SET LOCAL` + `ROLLBACK` is the whole safety property.** `SET LOCAL` scopes the identity
  switch to the transaction; nothing the probe writes survives. Assert it: after the rollback,
  run a COUNT for rows in the forbidden state and require 0.
- **`-v ON_ERROR_STOP=1` is what makes the assertion possible** — without it psql exits 0 after
  a failed statement and `RC` cannot distinguish refused from applied.
- **Distinguish a REFUSAL from a permission error.** `permission denied for function …` means
  the probe never reached the guard (see the probe-role grants above); the evidence you want is
  the guard's own message (e.g. `… has active slices; cannot complete`). Grant inside the txn to
  see the second one.
- **Set up the fixture INSIDE the txn too** — a story with an active child slice, a row in the
  state the arc requires — so the proof exercises the real precondition and leaves no row behind.

## Prove the DEPLOYED body, not just the version

`schema_version` advancing says the runner applied a file; it does not say the function you
are testing is the one you wrote.

```sql
SELECT position('<trusted-string-the-fix-removes>' IN
                pg_get_functiondef('<schema>.<function>(<argtypes>)'::regproc)) AS still_there,
       position('<new-predicate-the-fix-adds>' IN
                pg_get_functiondef('<schema>.<function>(<argtypes>)'::regproc)) AS now_present;
```

Require `still_there = 0` AND `now_present > 0`. A body that merely looks right in the repo
can be a deploy that never landed (unregistered migration, wrong DB, cached connection).

## Order of operations

1. Capture `pg_get_functiondef()` of every function you will replace BEFORE the deploy — the
   only "before" that will ever exist.
2. Battery RED (new migration moved aside) → GREEN, on the scratch DB.
3. Deploy, then the live proof above (rolled back) + the deployed-body probe + the residue count.
4. Re-run the battery AFTER the deploy: a guard that behaves on the scratch DB and not on the
   live one is a deploy problem, and step 3 is what tells the two apart.

## What this proves, and what it does not

It proves the guard refuses on THIS host's live store with real data. It does not prove the
legitimate path still works there — pair it with one approved transition driven the same way
(rolled back), or the evidence only shows that you can block things.
