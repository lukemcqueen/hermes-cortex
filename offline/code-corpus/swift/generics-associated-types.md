---
language: swift
tags: [swift, generic, associatedtype, where, constraint]
title: Generics & Associated Types
description: Covers generic functions, generic types, associatedtype in protocols, and where clauses for type constraints.
source: pattern
---

```swift
import Foundation

// Generic function
func swapValues<T>(_ a: inout T, _ b: inout T) {
    (a, b) = (b, a)
}

// Generic type with constraint
struct Stack<Element: Equatable> {
    private var storage: [Element] = []

    mutating func push(_ element: Element) { storage.append(element) }
    mutating func pop() -> Element? { storage.popLast() }
    func contains(_ element: Element) -> Bool { storage.contains(element) }
}

// Protocol with associatedtype
protocol Container {
    associatedtype Item
    mutating func append(_ item: Item)
    var count: Int { get }
}

// Generic conformance with where clause
extension Container where Item: Numeric {
    var total: Item { (0..<count).reduce(into: 0 as! Item) { _, _ in } }
}

// Concrete stack
var s = Stack<Int>()
s.push(1)
s.push(2)
print(s.contains(1))  // true

// where clause on function
func allEqual<T: Sequence>(_ seq: T) -> Bool where T.Element: Equatable {
    var iter = seq.makeIterator()
    guard let first = iter.next() else { return true }
    while let next = iter.next() {
        if first != next { return false }
    }
    return true
}

```
