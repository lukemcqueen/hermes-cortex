---
language: rust
tags: [pattern, util]
title: Result & Error Handling
description: Result<T, E>, the ? operator, unwrap/expect, map_err, and custom error types with thiserror.
source: pattern
---

```rust
use std::num::ParseIntError;
use thiserror::Error;

// --- Custom error type via thiserror ---
#[derive(Error, Debug)]
pub enum AppError {
    #[error("invalid input: {0}")]
    InvalidInput(String),
    #[error("parse error: {0}")]
    Parse(#[from] ParseIntError),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
}

// --- Function returning Result with ? operator ---
fn parse_and_double(input: &str) -> Result<i32, AppError> {
    let val: i32 = input.parse()?;            // ? propagates ParseIntError automatically
    if val < 0 {
        return Err(AppError::InvalidInput("negative number".into()));
    }
    Ok(val * 2)
}

fn main() -> Result<(), AppError> {
    // --- Basic Result usage ---
    let result = parse_and_double("42");
    match result {
        Ok(n) => println!("Got: {n}"),
        Err(e) => eprintln!("Error: {e}"),
    }

    // --- unwrap / expect (use sparingly — panic on error) ---
    let x = "10".parse::<i32>().expect("failed to parse");
    println!("{x}");

    // --- map_err to convert error types ---
    let data = std::fs::read_to_string("/nonexistent")
        .map_err(|e| AppError::Io(e))?;

    // --- if-let for Ok shorthand ---
    if let Ok(val) = parse_and_double("7") {
        println!("Doubled: {val}");
    }

    Ok(())
}

```
