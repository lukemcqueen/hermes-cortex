#!/usr/bin/env python3
"""Tiered verification of a parsed verse corpus against an independent reference dataset.

Compares a normalised record list against a bulk KJV dataset, reports four tiers
(exact / case-only / punctuation-insensitive / residual) and classifies the residual into
the known benign buckets so real differences stand out.

Usage
-----
  python3 verify_corpus.py --records records.json --reference en_kjv.json \
      [--n-books 39] [--show 15] [--dump residual.json]

records.json   JSON list of {"book", "chapter", "verse", "text"}. The book order of first
               appearance is taken as the corpus order (must match the reference order).
reference      Path or http(s) URL to a thiagobodruk/bible style file:
               [{"abbrev":..., "name":..., "chapters": [["verse text", ...], ...]}]
               Or a bible-api style dump: {"verses":[{"book_name","chapter","verse","text"}]}.
n-books        How many leading reference books to compare (39 = OT, 27 = NT, omit = all).

Exit code is 0 even when differences exist -- across editions they are expected, and the
worth is in the classification, not a pass/fail bit.
"""
import argparse
import collections
import json
import re
import unicodedata
import urllib.request


def load_ref(path):
    if path.startswith("http"):
        req = urllib.request.Request(path, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    else:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    if isinstance(data, dict):  # bible-api shaped dump
        books = collections.OrderedDict()
        for v in data.get("verses", []):
            books.setdefault(v["book_name"], {}).setdefault(v["chapter"], {})[v["verse"]] = v["text"]
        out = []
        for name, chaps in books.items():
            out.append({"name": name,
                        "chapters": [[ch.get(i, "") for i in range(1, max(ch) + 1)]
                                     for _, ch in sorted(chaps.items())]})
        return out
    return data


def strip_brackets(s):
    return s.replace("[", " ").replace("]", " ")


def t_exact(s):
    return re.sub(r"\s+", " ", strip_brackets(s)).strip()


def t_case(s):
    return t_exact(s).lower()


def t_punct(s):
    s = unicodedata.normalize("NFKC", t_case(s)).replace("\u2019", "'")
    return re.sub(r"[^a-z0-9]+", "", s)   # drops hyphens, spaces, italics, punctuation


def words(s):
    return re.findall(r"[a-z0-9]+", s.lower())


SPELLINGS = (("inquire", "enquire"), ("counseller", "counsellor"), ("rasor", "razor"),
             ("abida", "abidah"), ("jehovahnissi", "jehovah-nissi"),
             ("jehovahshalom", "jehovah-shalom"), ("ax", "axe"),
             ("lowering", "lowring"), ("instructors", "instructers"),
             ("sarah", "sara"), ("a heathen", "an heathen"),
             ("and cast", "and to cast"))


def classify(book, mine, ref):
    """Bucket a residual difference into the known benign classes."""
    if t_punct(book + mine).endswith(t_punct(ref)):
        return "superscription/title merged into verse 1 (reference drops it)"
    if re.search(r"(:\s*(or,|Heb\.|that is)|\btherefore, etc\b)", ref):
        return "reference dataset appends a marginal note"
    a, b = t_punct(mine), t_punct(ref)
    for x, y in SPELLINGS:
        for xv, yv in ((x, y), (x + "s", y + "s"), (x + "d", y + "d"), (x + "ing", y + "ing")):
            if a.replace(xv, yv) == b:
                return "edition house spelling: %s/%s" % (x, y)
    if t_punct(mine).startswith(t_punct(ref)) and len(t_punct(mine)) > len(t_punct(ref)):
        return "corpus keeps a printed subscription/appendix inside the verse (reference drops it)"
    extra = [w for w in words(ref) if w not in words(mine)]
    missing = [w for w in words(mine) if w not in words(ref)]
    if extra and not missing:
        return "reference adds words: %s" % ", ".join(sorted(set(extra))[:4])
    if missing and not extra:
        return "corpus adds words: %s" % ", ".join(sorted(set(missing))[:4])
    return "quoted EXCEPTION - spot-check this verse against a second source"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--n-books", type=int, default=0)
    ap.add_argument("--show", type=int, default=15)
    ap.add_argument("--dump")
    args = ap.parse_args()

    with open(args.records, encoding="utf-8") as fh:
        records = json.load(fh)
    ref = load_ref(args.reference)
    if args.n_books:
        ref = ref[: args.n_books]

    order, seen = [], set()
    for r in records:
        if r["book"] not in seen:
            seen.add(r["book"])
            order.append(r["book"])
    corpus = {}
    for r in records:
        corpus.setdefault(r["book"], {}).setdefault(r["chapter"], {})[r["verse"]] = r["text"]

    ref_names = [b.get("name") for b in ref]
    if order[: len(ref)] not in (ref_names, [b.get("abbrev") for b in ref]):
        print("WARNING: reference book order/names differ from corpus order (reference may be localised)")
        print("  corpus:", order[: len(ref)])
        print("  ref   :", ref_names[: len(order)])
        print("  -> comparing positionally; verify the pairing before trusting any count\n")

    tiers = collections.Counter()
    residual, struct = [], []
    for i, book in enumerate(order[: len(ref)]):
        rb = ref[i]
        n_mine = sum(len(c) for c in corpus.get(book, {}).values())
        n_ref = sum(len(c) for c in rb["chapters"])
        nch_mine, nch_ref = len(corpus.get(book, {})), len(rb["chapters"])
        flag = "" if (n_mine == n_ref and nch_mine == nch_ref) else "   <<< STRUCTURE MISMATCH"
        struct.append((book, n_mine, n_ref, nch_mine, nch_ref, flag))
        for ci, chap in enumerate(rb["chapters"], 1):
            for vi, txt in enumerate(chap, 1):
                mine = corpus.get(book, {}).get(ci, {}).get(vi)
                if mine is None:
                    tiers["missing"] += 1
                    residual.append((book, ci, vi, "MISSING", txt, "missing from corpus"))
                    continue
                if t_exact(mine) == t_exact(txt):
                    tiers["exact"] += 1
                elif t_case(mine) == t_case(txt):
                    tiers["case"] += 1
                elif t_punct(mine) == t_punct(txt):
                    tiers["punctuation"] += 1
                else:
                    tiers["residual"] += 1
                    residual.append((book, ci, vi, mine, txt, classify(book, mine, txt)))

    print("structure (book, verses mine/ref, chapters mine/ref):")
    for book, nm, nr, cm, cr, flag in struct:
        print("  %-18s%6d/%-6d  %3d/%-3d%s" % (book, nm, nr, cm, cr, flag))
    print("\ntiers:", dict(tiers), "| compared:", sum(tiers.values()))
    for k, n in collections.Counter(d[5] for d in residual).most_common():
        print("  %5d  %s" % (n, k))
    if residual and args.show:
        print("\nfirst residuals (mine | reference):")
        for book, ci, vi, mine, txt, cat in residual[: args.show]:
            print("\n%s %d:%d  [%s]\n  mine: %s\n  ref : %s" % (book, ci, vi, cat, mine[:160], txt[:160]))
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as fh:
            json.dump(residual, fh, ensure_ascii=False)
        print("\nresidual written to", args.dump)


if __name__ == "__main__":
    main()
