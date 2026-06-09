---
language: swift
tags: [swift, closure, higher-order, map, filter, reduce, escaping]
title: Closures & Higher-Order Functions
description: Covers closure syntax, trailing closures, shorthand arguments ($0), map/filter/reduce on collections, and @escaping / @autoclosure attributes.
source: pattern
---

```swift
import Foundation

let numbers = [1, 2, 3, 4, 5]

// Closure basics
let doubled = numbers.map { $0 * 2 }

// Trailing closure
let evens = numbers.filter { $0.isMultiple(of: 2) }

// reduce(into:) for accumulating
let grouped = numbers.reduce(into: [String: [Int]]()) { dict, n in
    let key = n.isMultiple(of: 2) ? "even" : "odd"
    dict[key, default: []].append(n)
}

// @escaping closure (stored for later)
final class CallbackStore {
    private var handlers: [(Int) -> Void] = []

    func addHandler(_ handler: @escaping (Int) -> Void) {
        handlers.append(handler)
    }

    func fireAll(value: Int) {
        handlers.forEach { $0(value) }
    }
}

// @autoclosure example
func assert(_ condition: @autoclosure () -> Bool) {
    if !condition() { fatalError("Assertion failed") }
}
assert(1 + 1 == 2)   // autoclosure defers evaluation

```
