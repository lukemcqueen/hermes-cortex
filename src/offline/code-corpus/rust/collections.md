---
language: rust
tags: [pattern, util]
title: Vectors, Strings & Collections
description: Vec, String, HashMap, HashSet, BTreeMap, iterators, and collect patterns.
source: pattern
---

```rust
use std::collections::{HashMap, HashSet, BTreeMap};

fn main() {
    // --- Vec ---
    let mut v: Vec<i32> = Vec::new();
    v.push(10);
    v.push(20);
    v.extend([30, 40]);
    println!("Vec: {v:?}, len={}, last={:?}", v.len(), v.last());

    // --- Vec from iterator ---
    let squares: Vec<i32> = (1..=5).map(|x| x * x).collect();
    println!("Squares: {squares:?}");

    // --- String ---
    let mut s = String::from("hello");
    s.push(' ');
    s.push_str("world");
    s += "!";
    let upper = s.to_uppercase();
    println!("String: {s} | Upper: {upper}");

    // --- HashMap ---
    let mut scores = HashMap::new();
    scores.insert("Alice", 95);
    scores.insert("Bob", 82);
    *scores.entry("Alice").or_insert(0) += 5;
    println!("HashMap: {scores:?}");

    for (name, score) in &scores {
        println!("  {name}: {score}");
    }

    // --- HashSet ---
    let mut seen = HashSet::new();
    for item in &[1, 2, 3, 2, 1, 4] {
        seen.insert(item);
    }
    println!("Unique: {seen:?} (len={})", seen.len());

    // --- BTreeMap (sorted keys) ---
    let mut tree = BTreeMap::new();
    tree.insert("z", 1);
    tree.insert("a", 2);
    tree.insert("m", 3);
    println!("BTreeMap (sorted): {tree:?}");
}

```
