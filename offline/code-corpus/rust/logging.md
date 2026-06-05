---
language: rust
tags: [pattern, util]
title: Logging
description: log crate with env_logger, tracing crate with spans, log levels, and structured fields.
source: pattern
---

```rust
// --- Setup (in main) ---
// With env_logger: RUST_LOG=info cargo run
// With tracing: RUST_LOG=info,my_crate=trace cargo run

use log::{info, warn, error, debug};
use tracing::{span, Level, instrument};

// --- Simple logging with log + env_logger ---
fn process_item(item: &str) {
    info!("Processing item: {item}");
    debug!("Item details: len={}", item.len());
    if item.is_empty() {
        warn!("Empty item encountered");
    }
}

fn read_config(path: &str) -> Result<String, std::io::Error> {
    info!("Reading config from {path}");
    let content = std::fs::read_to_string(path)?;
    Ok(content)
}

// --- Tracing with spans ---
#[instrument]   // auto-adds function name + args as span
fn compute_score(name: &str, value: i32) -> i32 {
    // Traced span created automatically
    let result = value * 2;
    tracing::info!(score = result, "Computed score");
    result
}

fn main() {
    // Initialize logger (call once at startup)
    env_logger::init();

    // --- log crate usage ---
    info!("Application started");
    process_item("hello");
    match read_config("config.toml") {
        Ok(cfg) => info!("Config loaded ({} bytes)", cfg.len()),
        Err(e) => error!("Failed to read config: {e}"),
    }

    // --- tracing span (manual) ---
    let parent_span = span!(Level::INFO, "request", id = 42);
    let _guard = parent_span.enter();
    tracing::info!("Processing request");
    compute_score("alice", 100);

    // --- Structured fields ---
    tracing::info!(
        user = "bob",
        action = "login",
        duration_ms = 45,
        "User logged in"
    );
}

```
