---
language: swift
tags: [swift, protocol, extension, associatedtype, protocol-composition]
title: Protocols & Protocol Extensions
description: Protocol definition, default implementations via protocol extensions, associated types, and protocol composition with & syntax.
source: pattern
---

```swift
import Foundation

// MARK: - Protocol declaration
protocol Identifiable {
    associatedtype ID: Hashable
    var id: ID { get }
}

// Default implementation via extension
extension Identifiable {
    var id: String { UUID().uuidString }
}

// Protocol composition
protocol Loggable: AnyObject {
    func log(_ message: String)
}

protocol Metricable {
    var metrics: [String: Double] { get }
}

typealias Monitored = Loggable & Metricable

// Conformance
final class Monitor: Monitored {
    var metrics: [String: Double] = [:]

    func log(_ message: String) {
        print("[Monitor] \(message)")
    }
}

// Constrained extension
extension Collection where Element: Numeric {
    var sum: Element { reduce(0, +) }
}

print([1, 2, 3].sum)  // 6

```
