---
language: swift
tags: [swift, property-wrapper, Published, AppStorage, State, custom-wrapper]
title: Property Wrappers
description: Shows Swift property wrappers: @Published, @AppStorage, @State, and building a custom property wrapper with projectedValue.
source: pattern
---

```swift
import Foundation
import SwiftUI

// MARK: - Built-in wrappers

final class ViewModel: ObservableObject {
    @Published var isLoaded = false
}

struct SettingsView: View {
    @AppStorage("theme") var theme: String = "light"
    @State private var counter = 0

    var body: some View {
        Text("theme: \(theme), count: \(counter)")
    }
}

// MARK: - Custom property wrapper
@propertyWrapper
struct Clamped<T: Comparable> {
    private var value: T
    private let range: ClosedRange<T>

    init(wrappedValue: T, _ range: ClosedRange<T>) {
        self.range = range
        self.value = min(max(wrappedValue, range.lowerBound), range.upperBound)
    }

    var wrappedValue: T {
        get { value }
        set { value = min(max(newValue, range.lowerBound), range.upperBound) }
    }

    // projectedValue exposes the raw (unclamped) set
    var projectedValue: Self { self }
}

struct VideoPlayer {
    @Clamped(0.0...1.0) var volume: Double = 0.5

    mutating func setVolumeRaw(_ raw: Double) {
        $volume.wrappedValue = raw  // bypass clamping via projectedValue
    }
}

```
