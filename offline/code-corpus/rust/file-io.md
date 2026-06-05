---
language: rust
tags: [io, file, pattern]
title: File I/O
description: std::fs read/write/create_dir/remove, std::io::BufReader/BufWriter, and OpenOptions.
source: pattern
---

```rust
use std::fs;
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::Path;

fn main() -> io::Result<()> {
    // --- Write a file (overwrite) ---
    fs::write("hello.txt", "Hello, world!
")?;
    println!("Wrote hello.txt");

    // --- Read entire file ---
    let content = fs::read_to_string("hello.txt")?;
    println!("Read: {content}");

    // --- Create directory ---
    fs::create_dir_all("data/subdir")?;

    // --- Write to file in subdirectory ---
    fs::write("data/subdir/note.txt", "Nested file content")?;

    // --- BufReader for line-by-line reading ---
    let file = fs::File::open("hello.txt")?;
    let reader = BufReader::new(file);
    for line in reader.lines() {
        println!("Line: {}", line?);
    }

    // --- BufWriter for buffered writing ---
    let file = fs::File::create("output.txt")?;
    let mut writer = BufWriter::new(file);
    writeln!(writer, "Buffered line 1")?;
    writeln!(writer, "Buffered line 2")?;
    writer.flush()?;   // ensure data is written
    println!("Wrote output.txt");

    // --- OpenOptions for append mode ---
    let mut file = fs::OpenOptions::new()
        .append(true)
        .create(true)
        .open("log.txt")?;
    writeln!(file, "Appended log entry")?;

    // --- Check existence and remove ---
    let path = "temp_file.txt";
    fs::write(path, "temporary")?;
    if Path::new(path).exists() {
        fs::remove_file(path)?;
        println!("Removed {path}");
    }

    // --- Remove directory ---
    fs::remove_dir_all("data")?;

    Ok(())
}

```
