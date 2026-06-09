---
language: swift
tags: [swift, Codable, JSON, JSONEncoder, JSONDecoder, CodingKeys, serialization]
title: Codable & JSON
description: Shows Swift's Codable system: automatic conformance, custom CodingKeys, JSONEncoder/Decoder, snake-case conversion, and date strategies.
source: pattern
---

```swift
import Foundation

// Automatic Codable
struct User: Codable {
    let id: Int
    let name: String
    let email: String?
}

// Custom CodingKeys
struct Article: Codable {
    let id: Int
    let title: String
    let publishedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case publishedAt = "published_at"
    }
}

let encoder = JSONEncoder()
encoder.keyEncodingStrategy = .convertToSnakeCase
encoder.dateEncodingStrategy = .iso8601

let decoder = JSONDecoder()
decoder.keyDecodingStrategy = .convertFromSnakeCase
decoder.dateDecodingStrategy = .iso8601

let json = #"{"id":1,"name":"Alice","email":"alice@example.com"}"#
if let data = json.data(using: .utf8),
   let user = try? decoder.decode(User.self, from: data) {
    print(user.name)
}

```
