---
language: rust
tags: [pattern, util]
title: Const & Static
description: const vs static, const fn, associated constants, and lazy_static/once_cell::sync::OnceCell.
source: pattern
---

```rust
use std::sync::OnceLock;

// --- const (compile-time, inlined) ---
const MAX_RETRIES: u32 = 5;
const APP_NAME: &str = "myapp";

/// const fn — evaluated at compile time
const fn factorial(n: u32) -> u32 {
    let mut result = 1;
    let mut i = 1;
    while i <= n {
        result *= i;
        i += 1;
    }
    result
}

const FACT_10: u32 = factorial(10);

// --- static (single address, mutable requires unsafe) ---
static VERSION: &str = "1.0.0";
static mut COUNTER: u32 = 0;   // mutable static requires unsafe

// --- Associated constants on types ---
trait MathConstants {
    const PI: f64;
}

struct Circle;
impl MathConstants for Circle {
    const PI: f64 = 3.141592653589793;
}

// --- OnceLock (thread-safe lazy init, no alloc) ---
static CONFIG: OnceLock<String> = OnceLock::new();

fn get_config() -> &'static str {
    CONFIG.get_or_init(|| {
        // Expensive one-time initialization
        std::fs::read_to_string("config.toml").unwrap_or_default()
    })
}

fn main() {
    println!("App: {APP_NAME}, max retries: {MAX_RETRIES}");
    println!("Factorial(10) = {FACT_10}");
    println!("Version: {VERSION}");
    println!("PI = {}", Circle::PI);

    // OnceLock lazy init
    println!("Config: {}", get_config());

    // Mutable static (unsafe)
    unsafe {
        COUNTER += 1;
        println!("Counter: {COUNTER}");
    }
}

```
