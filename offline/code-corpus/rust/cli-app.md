---
language: rust
tags: [cli, io]
title: CLI Application
description: Rust CLI app with clap argument parsing and error handling.
source: pattern
---

```rust
use std::fs;
use std::path::PathBuf;
use clap::Parser;

#[derive(Parser)]
#[command(name = "mytool", version, about = "Does awesome things")]
struct Cli {
    /// Input file path
    input: PathBuf,

    /// Output file path
    #[arg(short, long, default_value = "output.txt")]
    output: PathBuf,

    /// Verbose mode
    #[arg(short, long)]
    verbose: bool,

    /// Max items to process
    #[arg(long, default_value_t = 10)]
    limit: usize,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();

    if cli.verbose {
        eprintln!("Reading from: {:?}", cli.input);
        eprintln!("Writing to: {:?}", cli.output);
    }

    let content = fs::read_to_string(&cli.input)?;
    let processed = process_content(&content, cli.limit);
    fs::write(&cli.output, &processed)?;

    println!("Done. Wrote {} bytes to {:?}", processed.len(), cli.output);
    Ok(())
}

fn process_content(content: &str, _limit: usize) -> String {
    content.to_uppercase()
}

```
