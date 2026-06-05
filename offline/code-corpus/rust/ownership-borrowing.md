---
language: rust
tags: [pattern, util]
title: Ownership & Borrowing
description: Move semantics, borrowing &, mutable borrowing &mut, copy vs clone, and lifetime basics.
source: pattern
---

```rust
/// Ownership, borrowing, and lifetimes in Rust.
fn main() {
    // --- Move ---
    let s1 = String::from("hello");
    let s2 = s1;             // s1 is MOVED into s2
    // println!("{s1}");     // compile error — value used after move

    // --- Clone (deep copy) ---
    let t1 = String::from("world");
    let t2 = t1.clone();     // explicit deep copy
    println!("{t1} {t2}");   // both are usable

    // --- Copy types (stack-only) ---
    let x: u32 = 42;
    let y = x;               // Copy, not move: x is still valid
    println!("{x} {y}");

    // --- Borrow (&) ---
    let s = String::from("read-only");
    let len = compute_len(&s);
    println!("'{s}' has length {len}");   // s still usable

    // --- Mutable borrow (&mut) ---
    let mut m = String::from("hello");
    append_world(&mut m);
    println!("{m}");

    // --- Lifetime annotation ---
    let result = longest("abc", "xyz");
    println!("Longest: {result}");
}

fn compute_len(s: &String) -> usize {
    s.len()
}

fn append_world(s: &mut String) {
    s.push_str(", world");
}

/// Lifetime parameter 'a ties the return value to both inputs.
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

```
