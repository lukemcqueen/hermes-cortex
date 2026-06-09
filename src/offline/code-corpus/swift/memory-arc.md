---
language: swift
tags: [swift, ARC, weak, unowned, reference-cycle, capture-list, autoreleasepool]
title: Memory & ARC
description: Covers Automatic Reference Counting: weak/unowned references, reference cycles, capture lists in closures, and autoreleasepool.
source: pattern
---

```swift
import Foundation

// MARK: - Strong reference cycle
class Parent {
    let name: String
    var child: Child?

    init(name: String) { self.name = name }
    deinit { print("\(name) deinit") }
}

class Child {
    let name: String
    weak var parent: Parent?   // weak avoids cycle

    init(name: String) { self.name = name }
    deinit { print("\(name) deinit") }
}

var parent: Parent? = Parent(name: "Dad")
var child: Child? = Child(name: "Son")
parent?.child = child
child?.parent = parent

parent = nil  // both deinit because parent is weakly referenced
child = nil

// MARK: - Capture lists
final class Logger {
    var message: String = "Hello"

    func makeClosure() -> () -> Void {
        // [weak self] avoids retain cycle
        return { [weak self] in
            guard let self else { return }
            print(self.message)
        }
    }
}

// MARK: - autoreleasepool
autoreleasepool {
    for i in 0..<1000 {
        let _ = String(format: "%d", i)
    }
}

// MARK: - unowned (use when self will outlive closure)
final class Service {
    var handler: (() -> Void)?

    func setup() {
        handler = { [unowned self] in
            print("Handling with \(self)")
        }
    }
}

```
