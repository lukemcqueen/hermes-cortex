---
language: rust
tags: [pattern, util]
title: Traits & Generics
description: Trait definition, impl Trait for Type, generic functions, trait bounds, and the where clause.
source: pattern
---

```rust
// --- Define a trait ---
trait Summary {
    fn summarize(&self) -> String;

    /// Default method (can be overridden)
    fn author(&self) -> &str {
        "unknown"
    }
}

// --- Implement trait for a type ---
struct Article {
    title: String,
    content: String,
    author: String,
}

impl Summary for Article {
    fn summarize(&self) -> String {
        format!(""{}" by {}", self.title, self.author())
    }

    fn author(&self) -> &str {
        &self.author
    }
}

struct Tweet {
    username: String,
    text: String,
}

impl Summary for Tweet {
    fn summarize(&self) -> String {
        format!("@{}: {}", self.username, self.text)
    }
}

// --- Generic function with trait bound ---
fn notify<T: Summary>(item: &T) {
    println!("Breaking: {}", item.summarize());
}

// --- Multiple bounds via where clause ---
fn compare_summaries<T, U>(a: &T, b: &U) -> bool
where
    T: Summary,
    U: Summary,
{
    a.summarize() == b.summarize()
}

// --- Return impl Trait ---
fn make_tweet() -> impl Summary {
    Tweet {
        username: "rustacean".into(),
        text: "Loving Rust!".into(),
    }
}

fn main() {
    let article = Article {
        title: "Rust 2024".into(),
        content: "New features...".into(),
        author: "Jane".into(),
    };
    notify(&article);

    let tweet = make_tweet();
    notify(&tweet);

    println!("Same? {}", compare_summaries(&article, &tweet));

    // --- Generic struct ---
    struct Pair<T> { x: T, y: T }
    impl<T> Pair<T> {
        fn new(x: T, y: T) -> Self { Self { x, y } }
    }
    let p = Pair::new(1, 2);
    println!("Pair: ({}, {})", p.x, p.y);
}

```
