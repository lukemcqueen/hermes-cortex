---
language: rust
tags: [test, pattern]
title: Testing in Rust
description: cargo test, #[test], #[should_panic], #[cfg(test)], unit tests, integration tests, and test modules.
source: pattern
---

```rust
/// Main library function
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

/// Function we'll test for panics
pub fn safe_divide(a: i32, b: i32) -> i32 {
    if b == 0 {
        panic!("division by zero");
    }
    a / b
}

/// Function returning Result
pub fn parse_number(s: &str) -> Result<i32, String> {
    s.parse().map_err(|_| format!("cannot parse '{s}'"))
}

// --- Unit tests: compiled only during `cargo test` ---
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 2), 4);
        assert_ne!(add(1, 1), 3);
    }

    #[test]
    fn test_add_negative() {
        assert_eq!(add(-1, 1), 0);
    }

    #[test]
    #[should_panic(expected = "division by zero")]
    fn test_divide_by_zero() {
        safe_divide(10, 0);
    }

    #[test]
    fn test_parse_ok() -> Result<(), String> {
        let n = parse_number("42")?;
        assert_eq!(n, 42);
        Ok(())
    }

    #[test]
    fn test_parse_err() {
        assert!(parse_number("abc").is_err());
    }

    /// Test that runs with `cargo test -- --ignored`
    #[test]
    #[ignore]
    fn expensive_test() {
        assert!(true);
    }
}

/*
=== Integration test (in tests/integration_test.rs) ===

use my_crate::add;

#[test]
fn integration_add() {
    assert_eq!(add(10, 20), 30);
}
*/

```
