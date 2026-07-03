---
language: rust
tags: [pattern, util]
title: Iterators & Closures
description: iter, into_iter, map/filter/fold, chain, zip, custom iterators, and closure syntax.
source: pattern
---

```rust
fn main() {
    let nums = vec![1, 2, 3, 4, 5];

    // --- Map & Filter ---
    let doubled: Vec<i32> = nums.iter().map(|x| x * 2).collect();
    let evens: Vec<&i32> = nums.iter().filter(|x| *x % 2 == 0).collect();
    println!("Doubled: {doubled:?} | Evens: {evens:?}");

    // --- Fold (reduce) ---
    let sum: i32 = nums.iter().fold(0, |acc, x| acc + x);
    println!("Sum: {sum}");

    // --- Chain ---
    let a = vec![1, 2];
    let b = vec![3, 4];
    let chained: Vec<i32> = a.iter().chain(b.iter()).copied().collect();
    println!("Chained: {chained:?}");

    // --- Zip ---
    let names = vec!["Alice", "Bob", "Charlie"];
    let ages = vec![30, 25, 35];
    let pairs: Vec<(&str, i32)> = names.into_iter().zip(ages).collect();
    println!("Zipped: {pairs:?}");

    // --- Closure captures ---
    let factor = 3;
    let multiplier = |x: i32| x * factor;   // captures factor by reference
    println!("3 * 7 = {}", multiplier(7));

    // --- Custom iterator (Counter) ---
    let count: Vec<i32> = Counter::new(3, 8).collect();
    println!("Counter: {count:?}");
}

/// Custom iterator: yields values from start to end (exclusive)
struct Counter {
    current: i32,
    end: i32,
}

impl Counter {
    fn new(start: i32, end: i32) -> Self {
        Self { current: start, end }
    }
}

impl Iterator for Counter {
    type Item = i32;

    fn next(&mut self) -> Option<Self::Item> {
        if self.current < self.end {
            let val = self.current;
            self.current += 1;
            Some(val)
        } else {
            None
        }
    }
}

```
