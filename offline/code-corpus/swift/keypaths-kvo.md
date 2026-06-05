---
language: swift
tags: [swift, KeyPath, WritableKeyPath, KVO, subscript, observe]
title: Key Paths & KVO
description: Shows Swift key paths (\KeyPath), WritableKeyPath, subscript access by key path, and Cocoa Key-Value Observing with NSObject.
source: pattern
---

```swift
import Foundation

// KeyPath basics
struct Person {
    let name: String
    var age: Int
}

let alice = Person(name: "Alice", age: 30)
let namePath = \Person.name
print(alice[keyPath: namePath])  // Alice

// WritableKeyPath
var bob = Person(name: "Bob", age: 25)
let agePath = \Person.age
bob[keyPath: agePath] = 26
print(bob.age)  // 26

// KeyPaths as first-class values
func getValue<T, V>(_ obj: T, _ keyPath: KeyPath<T, V>) -> V {
    obj[keyPath: keyPath]
}
print(getValue(alice, \.name))

// KVO with NSObject
final class ObservablePerson: NSObject {
    @objc dynamic var name: String
    @objc dynamic var age: Int

    init(name: String, age: Int) {
        self.name = name
        self.age = age
    }
}

let observed = ObservablePerson(name: "Charlie", age: 40)
let observation = observed.observe(\.age, options: [.old, .new]) { obj, change in
    print("Age changed: \(change.oldValue ?? 0) -> \(change.newValue ?? 0)")
}
observed.age = 41
observation.invalidate()

```
