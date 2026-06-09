---
language: rust
tags: [cli, pattern]
title: Clap CLI (Derive API)
description: Clap derive API: subcommands, argument groups, env variable fallback, and value hints.
source: pattern
---

```rust
use clap::{Parser, Subcommand, ArgGroup, ValueHint};

// --- Top-level CLI with subcommands ---
#[derive(Parser)]
#[command(name = "taskctl", version, about = "Task manager CLI")]
struct Cli {
    /// Enable verbose logging (also from env var)
    #[arg(short, long, global = true, env = "TASKCTL_VERBOSE")]
    verbose: bool,

    /// Config file path
    #[arg(short, long, default_value = "config.toml", value_hint = ValueHint::FilePath)]
    config: String,

    #[command(subcommand)]
    command: Commands,
}

// --- Subcommands ---
#[derive(Subcommand)]
enum Commands {
    /// Add a new task
    Add {
        /// Task title
        title: String,
        /// Priority level
        #[arg(short, long, default_value_t = 5)]
        priority: u32,
    },
    /// List all tasks
    List {
        /// Filter by status
        #[arg(short, long)]
        status: Option<String>,
        /// Show all fields
        #[arg(short, long)]
        verbose: bool,
    },
    /// Remove a task
    #[command(arg_required_else_help = true)]
    Remove {
        /// Task ID to remove (conflicts with --all)
        #[arg(group = "remove_mode")]
        id: Option<u32>,
        /// Remove all completed tasks
        #[arg(long, group = "remove_mode")]
        all: bool,
    },
}

fn main() {
    let cli = Cli::parse();

    if cli.verbose {
        eprintln!("Config: {}", cli.config);
    }

    match &cli.command {
        Commands::Add { title, priority } => {
            println!("Adding task '{title}' with priority {priority}");
        }
        Commands::List { status, verbose } => {
            println!("Listing tasks (status: {status:?}, verbose: {verbose})");
        }
        Commands::Remove { id, all } => {
            if *all {
                println!("Removing all completed tasks");
            } else if let Some(task_id) = id {
                println!("Removing task {task_id}");
            }
        }
    }
}

```
