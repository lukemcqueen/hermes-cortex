---
language: rust
tags: [pattern, util]
title: Structs & Enums
description: Struct definition, tuple structs, unit structs, enum variants, and impl blocks with Self.
source: pattern
---

```rust
// --- Named struct ---
#[derive(Debug)]
struct User {
    username: String,
    email: String,
    active: bool,
}

// --- Tuple struct ---
#[derive(Debug)]
struct Color(u8, u8, u8);

// --- Unit struct (no fields) ---
struct Marker;

// --- Enum with variants ---
#[derive(Debug)]
enum Status {
    Active,
    Inactive,
    Pending { reason: String },   // struct variant
    Code(i32),                     // tuple variant
}

// --- impl block ---
impl User {
    /// Constructor (associated function, no &self)
    fn new(username: &str, email: &str) -> Self {
        Self {
            username: username.to_string(),
            email: email.to_string(),
            active: true,
        }
    }

    /// Method (takes &self)
    fn deactivate(&mut self) {
        self.active = false;
    }

    /// Method (takes &self)
    fn is_active(&self) -> bool {
        self.active
    }
}

impl Status {
    fn description(&self) -> &str {
        match self {
            Status::Active => "user is active",
            Status::Inactive => "user is inactive",
            Status::Pending { .. } => "approval pending",
            Status::Code(c) => match c {
                0 => "ok",
                _ => "error",
            },
        }
    }
}

fn main() {
    // --- Construction ---
    let mut user = User::new("alice", "alice@example.com");
    let black = Color(0, 0, 0);

    // --- Struct update syntax ---
    let guest = User {
        username: "guest".into(),
        ..user   // fill remaining fields from user
    };

    user.deactivate();
    println!("Active: {} | Guest: {}", user.is_active(), guest.username);

    // --- Enum matching ---
    let status = Status::Pending { reason: "email verification".into() };
    println!("Status: {}", status.description());
}

```
