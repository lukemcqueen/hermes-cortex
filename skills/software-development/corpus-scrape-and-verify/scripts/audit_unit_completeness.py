#!/usr/bin/env python3
"""Per-unit completeness audit for a scraped reference corpus.

Fails loudly when a unit (book/part/file) or a sub-unit (chapter/section) is
missing, empty or short, instead of trusting a total row count. Written because
a corpus that was short by exactly one unit still looked plausible in a total.

Usage:
    audit_unit_completeness.py --rows ROWS [--expect EXPECT.tsv]
                              [--unit-field unit] [--subunit-field chapter]
                              [--index-field verse] [--quiet]

ROWS     a .jsonl file, or a directory scanned recursively for .jsonl/.csv.
         Records need a unit name, a sub-unit number and an index number.
EXPECT   TSV, no header:  <unit><TAB><subunit><TAB><expected-row-count>
         Build it from an INDEPENDENT source (a different edition's division),
         never from the data under audit.

Exit 0 = every unit/sub-unit present with the expected count.
Exit 1 = gaps found (each one listed).
Without --expect a fully MISSING unit cannot be detected; the reference table is
the load-bearing input.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys


def load_rows(paths, unit_field, subunit_field, index_field):
    rows = []
    for path in paths:
        if path.endswith(".csv"):
            with open(path, newline="", encoding="utf-8") as fh:
                for rec in csv.DictReader(fh):
                    rows.append(rec)
        else:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
    return rows


def expand(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.endswith((".jsonl", ".csv")):
                        out.append(os.path.join(root, f))
        elif os.path.isfile(p):
            out.append(p)
        else:
            sys.exit(f"audit: no such path: {p}")
    return out


def field(rec, names):
    for n in names:
        if n in rec:
            return rec[n]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-unit completeness audit for a scraped corpus")
    ap.add_argument("--rows", nargs="+", required=True, help="jsonl file(s) or directory(ies)")
    ap.add_argument("--expect", help="TSV: unit<TAB>subunit<TAB>expected-count")
    ap.add_argument("--unit-field", default="unit", help="default: unit, book")
    ap.add_argument("--subunit-field", default="chapter", help="default: chapter, part")
    ap.add_argument("--index-field", default="verse", help="default: verse, index")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    paths = expand(args.rows)
    rows = load_rows(paths, args.unit_field, args.subunit_field, args.index_field)
    if not rows:
        sys.exit("audit: no rows loaded — check --rows")

    counts: dict = collections.defaultdict(collections.Counter)
    seen = collections.Counter()
    blank = 0
    for rec in rows:
        unit = field(rec, [args.unit_field, "unit", "book"])
        sub = field(rec, [args.subunit_field, "chapter", "part", "section"])
        idx = field(rec, [args.index_field, "verse", "index", "line"])
        if unit is None or sub is None:
            blank += 1
            continue
        counts[str(unit)][int(sub)] += 1
        seen[(str(unit), int(sub), -1 if idx is None else int(idx))] += 1

    problems = []
    for key, n in seen.items():
        if n > 1 and key[2] != -1:
            problems.append(f"duplicate row: unit={key[0]} sub={key[1]} index={key[2]} x{n}")
    if blank:
        problems.append(f"{blank} record(s) without a unit/sub-unit field")

    print(f"files scanned : {len(paths)}")
    print(f"rows loaded   : {len(rows)}")
    print(f"units found   : {len(counts)}")

    expected_units = None
    if args.expect:
        expected_units = collections.defaultdict(dict)
        with open(args.expect, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) != 3:
                    sys.exit(f"audit: bad --expect line (want unit<TAB>subunit<TAB>count): {line!r}")
                expected_units[parts[0]][int(parts[1])] = int(parts[2])

        for unit, subs in expected_units.items():
            if unit not in counts:
                problems.append(f"MISSING UNIT: {unit} (expected {len(subs)} sub-units)")
                continue
            got = counts[unit]
            missing = sorted(s for s in subs if s not in got)
            empty = sorted(s for s in got if got[s] == 0)
            short = [(s, got[s], subs[s]) for s in sorted(subs) if s in got and got[s] != subs[s]]
            if missing:
                problems.append(f"{unit}: missing sub-units {missing[:12]}{' ...' if len(missing) > 12 else ''}")
            if empty:
                problems.append(f"{unit}: empty sub-units {empty[:12]}")
            if short:
                detail = ", ".join(f"{s}:{g}!={e}" for s, g, e in short[:12])
                problems.append(f"{unit}: count mismatch {detail}")
            if not args.quiet:
                print(f"  {unit:<24} {len(got):>5}/{len(subs):<5} sub-units, {sum(got.values()):>7} rows")
    else:
        print("NOTE: no --expect given — a fully missing unit CANNOT be detected this way.")
        for unit in sorted(counts, key=lambda u: (len(u), u)):
            if not args.quiet:
                print(f"  {unit:<24} {len(counts[unit]):>5} sub-units, {sum(counts[unit].values()):>7} rows")

    if problems:
        print(f"\nFAIL — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nOK — every expected unit/sub-unit present with the expected row count.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
