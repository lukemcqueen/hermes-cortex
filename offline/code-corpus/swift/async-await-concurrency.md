---
language: swift
tags: [swift, async, await, Task, TaskGroup, Actor, MainActor, concurrency]
title: async/await & Concurrency
description: Covers Swift structured concurrency: async/await functions, Task, TaskGroup, Actor isolation, MainActor, and async let bindings.
source: pattern
---

```swift
import Foundation

// MARK: - Async function
func fetchUser(id: Int) async throws -> String {
    let url = URL(string: "https://api.example.com/user/\(id)")!
    let (data, _) = try await URLSession.shared.data(from: url)
    return String(decoding: data, as: UTF8.self)
}

// MARK: - Actor for isolation
actor Counter {
    private var value = 0
    func increment() { value += 1 }
    func getValue() -> Int { value }
}

// MARK: - Async let & TaskGroup
func loadAll() async throws -> [String] {
    async let user1 = fetchUser(id: 1)
    async let user2 = fetchUser(id: 2)

    // TaskGroup — dynamic concurrency
    let extra: [String] = try await withThrowingTaskGroup(of: String.self) { group in
        for id in 3...5 {
            group.addTask { try await fetchUser(id: id) }
        }
        return try await group.reduce(into: []) { $0.append($1) }
    }

    let firstTwo = try await [user1, user2]
    return firstTwo + extra
}

// MARK: - MainActor
@MainActor
final class ViewModel {
    var name: String = ""

    func updateUI() async {
        let fetched = try? await fetchUser(id: 1)
        name = fetched ?? "—"
    }
}

```
