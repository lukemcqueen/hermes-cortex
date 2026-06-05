---
language: swift
tags: [swift, Array, Dictionary, Set, map, filter, compactMap, reduce, zip, stride]
title: Collections & Iteration
description: Covers Swift collection types and functional iteration: map/filter/compactMap, forEach, zip, stride, reduce(into:), and Set operations.
source: pattern
---

```swift
import Foundation

let words = ["swift", "rust", "kotlin", "python", "go"]

// map / compactMap
let uppercased = words.map { $0.uppercased() }
let lengths = words.compactMap { $0.count > 2 ? $0.count : nil }

// filter
let longWords = words.filter { $0.count > 4 }

// reduce(into:)
let groupedByFirst = words.reduce(into: [Character: [String]]()) { acc, w in
    guard let first = w.first else { return }
    acc[first, default: []].append(w)
}

// zip
let ranks = Array(1...words.count)
for (rank, word) in zip(ranks, words) {
    print("\(rank). \(word)")
}

// stride
for i in stride(from: 0, to: words.count, by: 2) {
    print(words[i])
}

// Set algebra
let a: Set = [1, 2, 3, 4]
let b: Set = [3, 4, 5, 6]
print(a.intersection(b))  // [3, 4]
print(a.symmetricDifference(b))  // [1, 2, 5, 6]

// forEach
words.forEach { print($0) }

```
