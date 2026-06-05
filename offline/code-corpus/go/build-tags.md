---
language: go
tags: [pattern, build, platform]
title: Build Tags & Conditional Compilation
description: //go:build directives, file naming conventions, platform-specific code, and build tag constraints.
source: pattern
---

```go
package main

// This file compiles on all platforms; platform-specific logic
// is handled via build constraints in companion files.

// --- Build tag overview ---
//
// File naming conventions (automatically constrained):
//   *_linux.go    — Linux only
//   *_windows.go  — Windows only
//   *_darwin.go   — macOS only
//   *_unix.go     — Unix-like (Linux, macOS, *BSD, Solaris)
//   _test.go      — only in test builds (except *_test.go naming)
//
// Build tag syntax (at top of file, before package declaration):
//   //go:build linux
//   //go:build !windows
//   //go:build linux && amd64
//   //go:build linux || darwin
//   //go:build ignore              — file excluded from all builds
//
// Multiple tags (separate lines):
//   //go:build linux
//   //go:build cgo
//
// Common tags: linux, darwin, windows, unix, amd64, arm64, 386,
//   cgo, go1.18, go1.21, race, debug, test, ignore
//
// Custom tags (set at build time):
//   go build -tags "prod,enterprise"

// --- Conditional compilation with ! constraint ---

//go:build !prod

// DevConfig contains development-only settings.
var DevConfig = map[string]string{
	"log_level": "debug",
	"db_host":   "localhost",
}

// --- prod.go companion (would be separate file) ---
// //go:build prod
//
// package main
//
// var DevConfig = map[string]string{
// 	"log_level": "info",
// 	"db_host":   "prod.internal",
// }

// --- Function with multiple platform-specific implementations ---

// getDefaultPath returns the default config path (platform-specific).
// Real implementations live in *_unix.go / *_windows.go files.
func getDefaultPath() string {
	// Generic fallback; overridden per platform
	return "/etc/app/config.yaml"
}

// TODO: Companion files would define:
//
// File: config_unix.go
// //go:build !windows
// package main
// func getDefaultPath() string { return "/etc/app/config.yaml" }
//
// File: config_windows.go
// //go:build windows
// package main
// func getDefaultPath() string { return "C:\\ProgramData\\App\\config.yaml" }

// --- Feature flags via build tags ---

//go:build cgo

// WithCGO is true when CGO is enabled.
const WithCGO = true

// --- Version-gated feature ---

//go:build go1.21

// UseSlices is available in Go 1.21+ (uses slices package).
const UseSlices = true

func main() {
	println("Build tags demo")
	println("DevConfig:", DevConfig["log_level"])
	println("Default path:", getDefaultPath())
	println("WithCGO:", WithCGO)
	println("UseSlices:", UseSlices)
}

```
