#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Search the vendored PDF design template catalog (pdf-template-match skill).

Ported from pdf-design-skill by Gagan Sharma (MIT):
https://github.com/gaganmanit/pdf-design-skill

Usage:
    python catalog_search.py "<query>" [-n <max_results>]

Data lives in ../assets/pdf-design.csv (relative to this script).
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from math import log
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "references" / "pdf-design.csv"
MAX_RESULTS = 3

SEARCH_COLS = ["Template Name", "Category", "Keywords", "Best For"]
OUTPUT_COLS = [
    "Template Name", "Category", "Keywords", "Layout Spec", "Typography",
    "Color Palette", "Best For", "ReportLab Notes", "Source Image",
]


class BM25:
    """BM25 ranking algorithm for text search."""

    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.corpus = []
        self.doc_lengths = []
        self.avgdl = 0
        self.idf = {}
        self.doc_freqs = defaultdict(int)
        self.N = 0

    def tokenize(self, text):
        text = re.sub(r"[^\w\s]", " ", str(text).lower())
        return [w for w in text.split() if len(w) > 2]

    def fit(self, documents):
        self.corpus = [self.tokenize(doc) for doc in documents]
        self.N = len(self.corpus)
        if self.N == 0:
            return
        self.doc_lengths = [len(doc) for doc in self.corpus]
        self.avgdl = sum(self.doc_lengths) / self.N
        for doc in self.corpus:
            seen = set()
            for word in doc:
                if word not in seen:
                    self.doc_freqs[word] += 1
                    seen.add(word)
        for word, freq in self.doc_freqs.items():
            self.idf[word] = log((self.N - freq + 0.5) / (freq + 0.5) + 1)

    def score(self, query):
        query_tokens = self.tokenize(query)
        scores = []
        for idx, doc in enumerate(self.corpus):
            score = 0
            doc_len = self.doc_lengths[idx]
            term_freqs = defaultdict(int)
            for word in doc:
                term_freqs[word] += 1
            for token in query_tokens:
                if token in self.idf:
                    tf = term_freqs[token]
                    idf = self.idf[token]
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                    score += idf * numerator / denominator
            scores.append((idx, score))
        return sorted(scores, key=lambda x: x[1], reverse=True)


def search(query, max_results=MAX_RESULTS):
    if not DATA_FILE.exists():
        return {"error": f"Catalog not found: {DATA_FILE}", "query": query}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = list(csv.DictReader(f))
    documents = [" ".join(str(row.get(col, "")) for col in SEARCH_COLS) for row in data]
    bm25 = BM25()
    bm25.fit(documents)
    results = []
    for idx, score in bm25.score(query)[:max_results]:
        if score > 0:
            row = data[idx]
            results.append({col: row.get(col, "") for col in OUTPUT_COLS if col in row})
    return {"query": query, "file": DATA_FILE.name, "count": len(results), "results": results}


def format_results(result):
    out = [
        "## PDF Design Search Results",
        f"**Query:** {result['query']} | **Source:** {result['file']} | **Found:** {result['count']} results",
        "",
    ]
    for i, row in enumerate(result["results"], 1):
        out.append(f"### Result {i}")
        for col, val in row.items():
            out.append(f"- **{col}:** {val}")
        out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Search the PDF design template catalog")
    parser.add_argument("query", help="Search keywords (document type + mood + feature)")
    parser.add_argument("-n", "--max-results", type=int, default=MAX_RESULTS)
    args = parser.parse_args()
    result = search(args.query, args.max_results)
    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)
    if not result["results"]:
        print(f"No results for: {args.query} — try different keywords (type + mood + feature)")
        sys.exit(0)
    print(format_results(result))


if __name__ == "__main__":
    main()
