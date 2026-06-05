---
language: rust
tags: [pattern, async, net]
title: Tokio Async Runtime
description: tokio::main, async fn, tokio::spawn, tokio::join!, and tokio::time::sleep.
source: pattern
---

```rust
use tokio::time::{sleep, Duration};

// --- Async entry point ---
#[tokio::main]
async fn main() {
    // --- Sequential async ---
    println!("Step 1");
    sleep(Duration::from_millis(200)).await;
    println!("Step 2");

    // --- Concurrent tasks with tokio::join! ---
    let (r1, r2) = tokio::join!(fetch_data(1), fetch_data(2));
    println!("Results: {r1}, {r2}");

    // --- Spawning background tasks ---
    let handle = tokio::spawn(async {
        for i in 0..3 {
            sleep(Duration::from_millis(100)).await;
            println!("Background task: {i}");
        }
        "done"
    });
    println!("Spawned background task");

    // --- Do other work while background runs ---
    sleep(Duration::from_millis(250)).await;
    println!("Main task continuing...");

    // --- Await the background task ---
    let result = handle.await.expect("task panicked");
    println!("Background finished: {result}");
}

async fn fetch_data(id: u32) -> String {
    sleep(Duration::from_millis(150)).await;
    format!("data-{id}")
}

```
