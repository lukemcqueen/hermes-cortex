---
language: rust
tags: [rust, best-practices, idiomatic, safety]
title: Rust Best Practices
description: Ownership patterns, Result/Option idiomatic usage, builder pattern, impl Trait, RAII, clippy lints, and module structure
source: pattern
---

# Rust Best Practices

## Ownership Patterns
Borrow when you only need to read, take ownership when you need to store or transform:

```rust
fn summarize(data: &[String]) -> String {
    // Borrow — no ownership transfer
    data.iter()
        .enumerate()
        .map(|(i, s)| format!("{}: {}", i + 1, s))
        .collect::<Vec<_>>()
        .join("\n")
}

fn transform(mut data: Vec<String>) -> Vec<String> {
    // Take ownership — caller relinquishes
    data.push("Footer".into());
    data
}
```

## Result / Option Idiomatic Usage
Use combinators over `match` for simple chains:

```rust
use std::path::Path;

fn read_first_line(path: &Path) -> Result<String, Box<dyn std::error::Error>> {
    let content = std::fs::read_to_string(path)?;              // Propagate error
    let first = content.lines().next().ok_or("Empty file")?;   // Convert None -> Err
    Ok(first.to_string())
}

fn lookup_user(id: u32) -> Option<String> {
    let db = ["Alice", "Bob"];
    db.get(id as usize).map(|&s| s.to_string())  // map over Option
}
```

## Builder Pattern
Use the builder pattern for structs with many optional fields:

```rust
#[derive(Debug, Default)]
struct RequestBuilder {
    url: Option<String>,
    method: Option<String>,
    headers: Vec<(String, String)>,
}

impl RequestBuilder {
    fn new() -> Self {
        Self::default()
    }

    fn url(mut self, url: impl Into<String>) -> Self {
        self.url = Some(url.into());
        self
    }

    fn header(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.headers.push((key.into(), value.into()));
        self
    }

    fn build(self) -> Result<Request, &'static str> {
        let url = self.url.ok_or("URL is required")?;
        Ok(Request {
            url,
            method: self.method.unwrap_or_else(|| "GET".into()),
            headers: self.headers,
        })
    }
}

#[derive(Debug)]
struct Request {
    url: String,
    method: String,
    headers: Vec<(String, String)>,
}
```

## `impl Trait` in Arguments and Returns
Use `impl Trait` for simple generic cases:

```rust
fn print_items(items: impl Iterator<Item = impl std::fmt::Display>) {
    for item in items {
        println!("{}", item);
    }
}

// Return opaque type for encapsulation
fn make_counter() -> impl Iterator<Item = u32> {
    0u32..=10
}
```

## RAII (Resource Acquisition Is Initialization)
Let destructors handle cleanup — you rarely need manual `close()` or `free()`:

```rust
use std::fs::File;
use std::io::BufReader;

fn count_lines(path: &str) -> std::io::Result<usize> {
    let file = File::open(path)?;              // File opened here
    let reader = BufReader::new(file);         // Buffered here
    // Reader and File drop() automatically on scope exit
    Ok(reader.lines().count())
}
```

## Clippy Lints
Enforce with `clippy::all`, `clippy::pedantic`, and `clippy::nursery`:

```rust
#![deny(clippy::all, clippy::pedantic)]
// Prefer `is_empty()` over `len() == 0`
// Prefer `if let Some(x) = opt` over `match opt { Some(x) => …, None => {} }`
// Avoid `unwrap()` without a comment explaining why it's safe
```

## Module Structure
Organise with `mod.rs` or `module_name.rs` pattern:

```
src/
├── main.rs          # Entrypoint, thin
├── config.rs        # Top-level module
├── db/
│   ├── mod.rs       # Re-exports, public API
│   ├── models.rs    # Data structures
│   └── queries.rs   # Database logic
└── cli/
    ├── mod.rs
    └── args.rs
```

Keep `main.rs` thin — delegate to library code behind `lib.rs`.