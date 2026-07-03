---
language: rust
tags: [pattern, util]
title: Option & Pattern Matching
description: Option<T>, match, if let, while let, and combinators: map, and_then, unwrap_or.
source: pattern
---

```rust
fn main() {
    let items = vec![1, 2, 3];

    // --- match on Option ---
    let first = items.first();
    match first {
        Some(v) => println!("First: {v}"),
        None    => println!("Empty list"),
    }

    // --- if let for single-arm matching ---
    if let Some(v) = items.get(1) {
        println!("Second: {v}");
    }

    // --- Combinators ---
    let result = items
        .first()
        .map(|x| x * 10)                         // Some(1) -> Some(10)
        .filter(|x| x > &5)                      // Some(10) stays
        .map(|x| format!("Value: {x}"))
        .unwrap_or_else(|| "fallback".into());
    println!("{result}");

    // --- and_then for chaining fallible ops ---
    let parsed = "42"
        .parse::<i32>()
        .ok()                                     // Result -> Option
        .and_then(|n| if n > 0 { Some(n * 2) } else { None });
    println!("Parsed: {parsed:?}");

    // --- while let (loop over iterator until None) ---
    let mut iter = vec!["a", "b", "c"].into_iter();
    while let Some(s) = iter.next() {
        print!("{s} ");
    }
    println!();

    // --- unwrap_or / unwrap_or_default ---
    let none: Option<i32> = None;
    let val = none.unwrap_or(-1);
    let def: i32 = none.unwrap_or_default();
    println!("{val} {def}");
}

```
