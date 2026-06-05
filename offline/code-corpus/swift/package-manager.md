---
language: swift
tags: [swift, Package, SwiftPM, Package.swift, dependencies, targets, products]
title: Package Manager (SwiftPM)
description: Shows a complete Package.swift manifest: dependencies, targets, products, and how to structure an SPM package with an executable and library.
source: pattern
---

```swift
// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "MyLibrary",
    platforms: [
        .macOS(.v13),
        .iOS(.v16),
    ],
    products: [
        // Library product
        .library(
            name: "MyLibrary",
            targets: ["MyLibrary"]
        ),
        // Executable product
        .executable(
            name: "my-tool",
            targets: ["MyTool"]
        ),
    ],
    dependencies: [
        // Remote package dependency
        .package(url: "https://github.com/apple/swift-argument-parser",
                 from: "1.2.0"),
        // Local package dependency
        .package(path: "../LocalHelpers"),
    ],
    targets: [
        // Main library target
        .target(
            name: "MyLibrary",
            dependencies: [
                .product(name: "ArgumentParser",
                         package: "swift-argument-parser"),
            ],
            swiftSettings: [
                .enableUpcomingFeature("BareSlashRegexLiterals"),
            ]
        ),
        // Executable target
        .executableTarget(
            name: "MyTool",
            dependencies: ["MyLibrary"]
        ),
        // Test target
        .testTarget(
            name: "MyLibraryTests",
            dependencies: ["MyLibrary"]
        ),
    ]
)

```
