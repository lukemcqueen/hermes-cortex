---
language: swift
tags: [swift, throws, try, catch, Result, Error, custom-error]
title: Error Handling
description: Shows Swift error handling: Error protocol, throwing functions, do/try/catch, Result type, try? vs try!, and custom error enums.
source: pattern
---

```swift
import Foundation

// MARK: - Custom error
enum FileError: Error, CustomStringConvertible {
    case notFound(path: String)
    case permissionDenied
    case corrupted(reason: String)

    var description: String {
        switch self {
        case .notFound(let path): return "File not found: \(path)"
        case .permissionDenied:   return "Permission denied"
        case .corrupted(let r):   return "Corrupted: \(r)"
        }
    }
}

// Throwing function
func readConfig(at path: String) throws -> String {
    guard FileManager.default.fileExists(atPath: path) else {
        throw FileError.notFound(path: path)
    }
    return try String(contentsOfFile: path, encoding: .utf8)
}

// do / try / catch
do {
    let content = try readConfig(at: "/etc/hosts")
    print(content)
} catch let error as FileError {
    print("File error: \(error)")
} catch {
    print("Other error: \(error.localizedDescription)")
}

// try? — optional result
if let content = try? readConfig(at: "/etc/hosts") {
    print("Got \(content.count) bytes")
}

// Result type
func fetchConfig() -> Result<String, FileError> {
    Result { try readConfig(at: "/etc/hosts") }
}

```
