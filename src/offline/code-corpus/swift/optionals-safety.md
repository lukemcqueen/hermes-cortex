---
language: swift
tags: [swift, optional, if-let, guard-let, nil-coalescing, optional-chaining]
title: Optionals & Safety
description: Shows Swift's optional system: if-let, guard-let, nil-coalescing (??), optional chaining, and map/flatMap on Optional values.
source: pattern
---

```swift
import Foundation

let dict: [String: Any] = ["name": "Alice", "age": 30, "email": nil]

// if-let binding
if let name = dict["name"] as? String {
    print("Name is \(name)")
}

// guard-let (early exit)
func greet(_ user: [String: Any]) {
    guard let name = user["name"] as? String else { return }
    print("Hello, \(name)!")
}

// nil coalescing
let displayName = (dict["name"] as? String) ?? "Guest"

// Optional chaining
let uppercased = (dict["name"] as? String)?.uppercased()

// map / flatMap on Optional
let length: Int? = (dict["name"] as? String).map(\.count)
let doubled: Int? = length.flatMap { $0 > 0 ? $0 * 2 : nil }

```
