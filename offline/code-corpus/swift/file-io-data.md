---
language: swift
tags: [swift, FileManager, JSONEncoder, JSONDecoder, Data, Bundle, file-io]
title: File I/O & Data
description: Shows reading/writing files with FileManager, encoding/decoding JSON to/from files, working with Data, Bundle resources, and String(contentsOf:).
source: pattern
---

```swift
import Foundation

let fm = FileManager.default
let documents = fm.urls(for: .documentDirectory, in: .userDomainMask).first!
let fileURL = documents.appendingPathComponent("data.json")

// Writing JSON to file
struct Person: Codable {
    let name: String
    let age: Int
}

let people = [Person(name: "Alice", age: 30), Person(name: "Bob", age: 25)]

do {
    let data = try JSONEncoder().encode(people)
    try data.write(to: fileURL, options: .atomic)
} catch {
    print("Write error: \(error)")
}

// Reading JSON from file
do {
    let data = try Data(contentsOf: fileURL)
    let decoded = try JSONDecoder().decode([Person].self, from: data)
    print(decoded)
} catch {
    print("Read error: \(error)")
}

// Reading from Bundle
if let bundleURL = Bundle.main.url(forResource: "config", withExtension: "json"),
   let content = try? String(contentsOf: bundleURL, encoding: .utf8) {
    print(content)
}

// FileManager operations
let tempDir = fm.temporaryDirectory
let tempFile = tempDir.appendingPathComponent(UUID().uuidString + ".txt")
try? "hello".write(to: tempFile, atomically: true, encoding: .utf8)
try? fm.removeItem(at: tempFile)

```
