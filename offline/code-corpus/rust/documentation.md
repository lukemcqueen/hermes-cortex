---
language: rust
tags: [pattern, util]
title: Documentation
description: //! inner doc (module level), /// outer doc, doc tests, cargo doc, and the #[doc] attribute.
source: pattern
---

```rust
//! # Rust Documentation Patterns
//!
//! This module demonstrates Rust documentation conventions.
//! Inner doc comments (`//!`) document the containing item (module, crate).
//!
//! Run `cargo doc --open` to see the rendered documentation.
//! Doc tests are run with `cargo test`.

/// Represents a 2D point in Cartesian coordinates.
///
/// # Examples
///
/// ```
/// use my_crate::Point;
///
/// let p = Point::new(3.0, 4.0);
/// assert_eq!(p.x(), 3.0);
/// ```
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Point {
    x: f64,
    y: f64,
}

impl Point {
    /// Create a new `Point`.
    ///
    /// # Arguments
    ///
    /// * `x` — The x-coordinate
    /// * `y` — The y-coordinate
    ///
    /// # Example
    ///
    /// ```
    /// let p = Point::new(1.0, 2.0);
    /// ```
    pub fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    /// Returns the x-coordinate.
    pub fn x(&self) -> f64 {
        self.x
    }

    /// Returns the y-coordinate.
    pub fn y(&self) -> f64 {
        self.y
    }

    /// Compute the distance between two points.
    ///
    /// This is a **doc test** that `cargo test` will run:
    ///
    /// ```
    /// use my_crate::Point;
    ///
    /// let a = Point::new(0.0, 0.0);
    /// let b = Point::new(3.0, 4.0);
    /// assert!((a.distance(&b) - 5.0).abs() < 1e-10);
    /// ```
    ///
    /// # Panics
    ///
    /// This method does not panic.
    pub fn distance(&self, other: &Point) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        (dx * dx + dy * dy).sqrt()
    }
}

/// This test is hidden from the docs but still run by `cargo test`.
///
/// ```ignore
/// // This code is ignored during doc tests
/// ```
#[doc(hidden)]
pub fn internal_helper() -> i32 {
    42
}

/// The [`Point`] unit — see the [module-level docs](#).
///
/// You can also link to items: [`Point::new`], [`Point::distance`].
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_point() {
        let p = Point::new(1.0, 2.0);
        assert_eq!(p.x(), 1.0);
        assert_eq!(p.y(), 2.0);
    }

    #[test]
    fn test_distance() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(3.0, 4.0);
        assert!((a.distance(&b) - 5.0).abs() < 1e-10);
    }
}

```
