---
language: swift
tags: [swift, SwiftUI, View, State, Binding, ObservedObject, modifier]
title: SwiftUI Basics
description: Covers fundamental SwiftUI patterns: View protocol, @State, @Binding, @ObservedObject, layout containers (VStack/HStack/ZStack), and common modifiers.
source: pattern
---

```swift
import SwiftUI

// MARK: - Simple view with @State
struct CounterView: View {
    @State private var count = 0

    var body: some View {
        VStack(spacing: 16) {
            Text("Count: \(count)")
                .font(.title)

            HStack {
                Button("-") { count -= 1 }
                Button("+") { count += 1 }
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}

// MARK: - Parent passing @Binding
struct ParentView: View {
    @State private var text = ""

    var body: some View {
        VStack {
            TextField("Type here", text: $text)
                .textFieldStyle(.roundedBorder)
            ChildView(text: $text)
        }
    }
}

struct ChildView: View {
    @Binding var text: String

    var body: some View {
        Text("You typed: \(text)")
            .foregroundColor(.secondary)
    }
}

// MARK: - ObservableObject pattern
final class SettingsViewModel: ObservableObject {
    @Published var volume: Double = 0.5
}

struct SettingsView: View {
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        Slider(value: $viewModel.volume, in: 0...1)
    }
}

```
