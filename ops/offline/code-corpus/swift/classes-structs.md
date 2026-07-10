---
language: swift
tags: [swift, class, struct, enum, value-semantics, reference-semantics, mutating]
title: Classes, Structs & Enums
description: Demonstrates Swift value types (struct/enum) vs reference types (class), mutating methods, enum associated values, and how copying semantics differ.
source: pattern
---

```swift
import Foundation

// MARK: - Value type (struct)
struct Point {
    var x: Double
    var y: Double

    mutating func translate(dx: Double, dy: Double) {
        x += dx
        y += dy
    }
}

// MARK: - Reference type (class)
class Person {
    let name: String
    var age: Int

    init(name: String, age: Int) {
        self.name = name
        self.age = age
    }

    func haveBirthday() { age += 1 }
}

// MARK: - Enum with associated values
enum NetworkResult {
    case success(data: Data)
    case failure(error: Error, statusCode: Int)
    case notModified

    var isSuccess: Bool {
        if case .success = self { return true }
        return false
    }
}

// Value semantics demo
var p1 = Point(x: 1, y: 2)
var p2 = p1          // independent copy
p2.translate(dx: 5, dy: 5)
print(p1)            // Point(x: 1.0, y: 2.0)
print(p2)            // Point(x: 6.0, y: 7.0)

// Reference semantics demo
let alice = Person(name: "Alice", age: 30)
let bob = alice      // same instance
bob.haveBirthday()
print(alice.age)     // 31 — aliased mutation
print(bob.age)       // 31

```
