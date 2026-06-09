---
language: rust
tags: [pattern, util]
title: Cargo Workspaces
description: Workspace [members], workspace dependencies, path deps, and feature propagation.
source: pattern
---

```rust
/*
=== FILE: Cargo.toml (workspace root) ===
[workspace]
members = [
    "crates/lib-core",
    "crates/cli",
    "crates/server",
]
resolver = "2"

# Shared dependencies (available to all members)
[workspace.dependencies]
serde = { version = "1", features = ["derive"] }
tokio = { version = "1", features = ["full"] }
anyhow = "1"

[workspace.package]
version = "0.1.0"
edition = "2021"
license = "MIT"

=== FILE: crates/lib-core/Cargo.toml ===
[package]
name = "lib-core"
version.workspace = true
edition.workspace = true

[dependencies]
serde.workspace = true
thiserror = "2"

=== FILE: crates/cli/Cargo.toml ===
[package]
name = "cli"
version.workspace = true
edition.workspace = true

[dependencies]
# Path dependency to sibling crate
lib-core = { path = "../lib-core" }
clap = { version = "4", features = ["derive"] }
anyhow.workspace = true
tokio.workspace = true

=== FILE: crates/server/Cargo.toml ===
[package]
name = "server"
version.workspace = true
edition.workspace = true

[dependencies]
lib-core = { path = "../lib-core" }
tokio.workspace = true
serde.workspace = true

[features]
default = ["lib-core/default"]
metrics = ["lib-core/metrics"]   # propagate feature to dep
*/

```
