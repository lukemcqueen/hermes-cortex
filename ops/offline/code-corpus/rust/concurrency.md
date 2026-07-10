---
language: rust
tags: [pattern, async]
title: Concurrency
description: std::thread, mpsc channels, Arc<Mutex>, parking_lot, and rayon parallel iterators.
source: pattern
---

```rust
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

fn main() {
    // --- Basic thread spawn ---
    let handle = thread::spawn(|| {
        for i in 1..=3 {
            println!("Spawned thread: {i}");
            thread::sleep(Duration::from_millis(50));
        }
        42
    });
    let result = handle.join().unwrap();
    println!("Thread returned: {result}");

    // --- mpsc channel (multi-producer, single-consumer) ---
    let (tx, rx) = mpsc::channel();
    let tx2 = tx.clone();

    thread::spawn(move || {
        tx.send("from thread 1").unwrap();
    });
    thread::spawn(move || {
        tx2.send("from thread 2").unwrap();
    });

    for received in rx {
        println!("Channel received: {received}");
    }

    // --- Arc<Mutex> for shared mutable state ---
    let counter = Arc::new(Mutex::new(0));
    let mut handles = vec![];

    for _ in 0..10 {
        let counter = Arc::clone(&counter);
        handles.push(thread::spawn(move || {
            let mut num = counter.lock().unwrap();
            *num += 1;
        }));
    }
    for h in handles {
        h.join().unwrap();
    }
    println!("Counter: {}", *counter.lock().unwrap());

    // --- Rayon parallel iterator ---
    let numbers: Vec<u64> = (1..=100).collect();
    let sum: u64 = numbers.par_iter().sum();
    println!("Parallel sum: {sum}");
}

```
