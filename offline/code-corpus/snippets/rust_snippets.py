"""Rust snippets — 20 entries covering core Rust patterns.

The existing core_snippets.py already ships rust/cli-app.md (Clap CLI).
These 20 snippets cover complementary Rust patterns.
"""

SNIPPETS = [
    # ═══════════════════════════════════════════════════════════
    # 1. OWNERSHIP & BORROWING
    # ═══════════════════════════════════════════════════════════
    ("rust/ownership-borrowing.md", "rust", ["pattern", "util"],
     "Ownership & Borrowing",
     "Move semantics, borrowing &, mutable borrowing &mut, copy vs clone, and lifetime basics.",
     "pattern",
     """/// Ownership, borrowing, and lifetimes in Rust.
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 2. RESULT & ERROR HANDLING
    # ═══════════════════════════════════════════════════════════
    ("rust/result-error-handling.md", "rust", ["pattern", "util"],
     "Result & Error Handling",
     "Result<T, E>, the ? operator, unwrap/expect, map_err, and custom error types with thiserror.",
     "pattern",
     """use std::num::ParseIntError;
use thiserror::Error;

// --- Custom error type via thiserror ---
#[derive(Error, Debug)]
pub enum AppError {
    #[error("invalid input: {0}")]
    InvalidInput(String),
    #[error("parse error: {0}")]
    Parse(#[from] ParseIntError),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
}

// --- Function returning Result with ? operator ---
fn parse_and_double(input: &str) -> Result<i32, AppError> {
    let val: i32 = input.parse()?;            // ? propagates ParseIntError automatically
    if val < 0 {
        return Err(AppError::InvalidInput("negative number".into()));
    }
    Ok(val * 2)
}

fn main() -> Result<(), AppError> {
    // --- Basic Result usage ---
    let result = parse_and_double("42");
    match result {
        Ok(n) => println!("Got: {n}"),
        Err(e) => eprintln!("Error: {e}"),
    }

    // --- unwrap / expect (use sparingly — panic on error) ---
    let x = "10".parse::<i32>().expect("failed to parse");
    println!("{x}");

    // --- map_err to convert error types ---
    let data = std::fs::read_to_string("/nonexistent")
        .map_err(|e| AppError::Io(e))?;

    // --- if-let for Ok shorthand ---
    if let Ok(val) = parse_and_double("7") {
        println!("Doubled: {val}");
    }

    Ok(())
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 3. OPTION & PATTERN MATCHING
    # ═══════════════════════════════════════════════════════════
    ("rust/option-pattern-matching.md", "rust", ["pattern", "util"],
     "Option & Pattern Matching",
     "Option<T>, match, if let, while let, and combinators: map, and_then, unwrap_or.",
     "pattern",
     """fn main() {
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 4. STRUCTS & ENUMS
    # ═══════════════════════════════════════════════════════════
    ("rust/structs-enums.md", "rust", ["pattern", "util"],
     "Structs & Enums",
     "Struct definition, tuple structs, unit structs, enum variants, and impl blocks with Self.",
     "pattern",
     """// --- Named struct ---
#[derive(Debug)]
struct User {
    username: String,
    email: String,
    active: bool,
}

// --- Tuple struct ---
#[derive(Debug)]
struct Color(u8, u8, u8);

// --- Unit struct (no fields) ---
struct Marker;

// --- Enum with variants ---
#[derive(Debug)]
enum Status {
    Active,
    Inactive,
    Pending { reason: String },   // struct variant
    Code(i32),                     // tuple variant
}

// --- impl block ---
impl User {
    /// Constructor (associated function, no &self)
    fn new(username: &str, email: &str) -> Self {
        Self {
            username: username.to_string(),
            email: email.to_string(),
            active: true,
        }
    }

    /// Method (takes &self)
    fn deactivate(&mut self) {
        self.active = false;
    }

    /// Method (takes &self)
    fn is_active(&self) -> bool {
        self.active
    }
}

impl Status {
    fn description(&self) -> &str {
        match self {
            Status::Active => "user is active",
            Status::Inactive => "user is inactive",
            Status::Pending { .. } => "approval pending",
            Status::Code(c) => match c {
                0 => "ok",
                _ => "error",
            },
        }
    }
}

fn main() {
    // --- Construction ---
    let mut user = User::new("alice", "alice@example.com");
    let black = Color(0, 0, 0);

    // --- Struct update syntax ---
    let guest = User {
        username: "guest".into(),
        ..user   // fill remaining fields from user
    };

    user.deactivate();
    println!("Active: {} | Guest: {}", user.is_active(), guest.username);

    // --- Enum matching ---
    let status = Status::Pending { reason: "email verification".into() };
    println!("Status: {}", status.description());
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 5. TRAITS & GENERICS
    # ═══════════════════════════════════════════════════════════
    ("rust/traits-generics.md", "rust", ["pattern", "util"],
     "Traits & Generics",
     "Trait definition, impl Trait for Type, generic functions, trait bounds, and the where clause.",
     "pattern",
     """// --- Define a trait ---
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
        format!("\"{}\" by {}", self.title, self.author())
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 6. VECTORS, STRINGS & COLLECTIONS
    # ═══════════════════════════════════════════════════════════
    ("rust/collections.md", "rust", ["pattern", "util"],
     "Vectors, Strings & Collections",
     "Vec, String, HashMap, HashSet, BTreeMap, iterators, and collect patterns.",
     "pattern",
     """use std::collections::{HashMap, HashSet, BTreeMap};

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
"""),

    # ═══════════════════════════════════════════════════════════
    # 7. ITERATORS & CLOSURES
    # ═══════════════════════════════════════════════════════════
    ("rust/iterators-closures.md", "rust", ["pattern", "util"],
     "Iterators & Closures",
     "iter, into_iter, map/filter/fold, chain, zip, custom iterators, and closure syntax.",
     "pattern",
     """fn main() {
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 8. SERDE SERIALIZATION
    # ═══════════════════════════════════════════════════════════
    ("rust/serde-serialization.md", "rust", ["pattern", "io"],
     "Serde Serialization",
     "serde::{Serialize, Deserialize}, #[serde(rename)], json::to_string/from_str, and custom serde.",
     "pattern",
     """use serde::{Deserialize, Serialize};
use serde_json;

// --- Basic struct ---
#[derive(Debug, Serialize, Deserialize)]
struct Person {
    name: String,
    age: u8,
}

// --- Renamed fields & default values ---
#[derive(Debug, Serialize, Deserialize)]
struct Config {
    #[serde(rename = "db_url")]
    database_url: String,
    #[serde(default = "default_port")]
    port: u16,
    #[serde(default)]
    debug: bool,
}

fn default_port() -> u16 { 5432 }

// --- Enum serialization ---
#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type")]        // internally tagged enum
enum Message {
    Text { content: String },
    Image { url: String, alt: Option<String> },
}

fn main() -> Result<(), serde_json::Error> {
    // --- Serialize to JSON string ---
    let person = Person { name: "Alice".into(), age: 30 };
    let json = serde_json::to_string_pretty(&person)?;
    println!("Serialized:\n{json}");

    // --- Deserialize from JSON string ---
    let data = r#"{"name":"Bob","age":25}"#;
    let parsed: Person = serde_json::from_str(data)?;
    println!("Deserialized: {parsed:?}");

    // --- Config with renames and defaults ---
    let cfg_str = r#"{"db_url":"postgres://localhost/mydb"}"#;   // port defaulted
    let config: Config = serde_json::from_str(cfg_str)?;
    println!("Config: port={}, debug={}", config.port, config.debug);

    // --- Enum round-trip ---
    let msg = Message::Text { content: "hello".into() };
    let msg_json = serde_json::to_string(&msg)?;
    let msg_back: Message = serde_json::from_str(&msg_json)?;
    println!("Enum round-trip: {msg_back:?}");

    Ok(())
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 9. TOKIO ASYNC RUNTIME
    # ═══════════════════════════════════════════════════════════
    ("rust/tokio-async.md", "rust", ["pattern", "async", "net"],
     "Tokio Async Runtime",
     "tokio::main, async fn, tokio::spawn, tokio::join!, and tokio::time::sleep.",
     "pattern",
     """use tokio::time::{sleep, Duration};

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
"""),

    # ═══════════════════════════════════════════════════════════
    # 10. CLAP CLI (derive API — different focus from core's cli-app.md)
    # ═══════════════════════════════════════════════════════════
    ("rust/clap-cli.md", "rust", ["cli", "pattern"],
     "Clap CLI (Derive API)",
     "Clap derive API: subcommands, argument groups, env variable fallback, and value hints.",
     "pattern",
     """use clap::{Parser, Subcommand, ArgGroup, ValueHint};

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
"""),

    # ═══════════════════════════════════════════════════════════
    # 11. TESTING
    # ═══════════════════════════════════════════════════════════
    ("rust/testing.md", "rust", ["test", "pattern"],
     "Testing in Rust",
     "cargo test, #[test], #[should_panic], #[cfg(test)], unit tests, integration tests, and test modules.",
     "pattern",
     """/// Main library function
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

/// Function we'll test for panics
pub fn safe_divide(a: i32, b: i32) -> i32 {
    if b == 0 {
        panic!("division by zero");
    }
    a / b
}

/// Function returning Result
pub fn parse_number(s: &str) -> Result<i32, String> {
    s.parse().map_err(|_| format!("cannot parse '{s}'"))
}

// --- Unit tests: compiled only during `cargo test` ---
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 2), 4);
        assert_ne!(add(1, 1), 3);
    }

    #[test]
    fn test_add_negative() {
        assert_eq!(add(-1, 1), 0);
    }

    #[test]
    #[should_panic(expected = "division by zero")]
    fn test_divide_by_zero() {
        safe_divide(10, 0);
    }

    #[test]
    fn test_parse_ok() -> Result<(), String> {
        let n = parse_number("42")?;
        assert_eq!(n, 42);
        Ok(())
    }

    #[test]
    fn test_parse_err() {
        assert!(parse_number("abc").is_err());
    }

    /// Test that runs with `cargo test -- --ignored`
    #[test]
    #[ignore]
    fn expensive_test() {
        assert!(true);
    }
}

/*
=== Integration test (in tests/integration_test.rs) ===

use my_crate::add;

#[test]
fn integration_add() {
    assert_eq!(add(10, 20), 30);
}
*/
"""),

    # ═══════════════════════════════════════════════════════════
    # 12. CONCURRENCY
    # ═══════════════════════════════════════════════════════════
    ("rust/concurrency.md", "rust", ["pattern", "async"],
     "Concurrency",
     "std::thread, mpsc channels, Arc<Mutex>, parking_lot, and rayon parallel iterators.",
     "pattern",
     """use std::sync::mpsc;
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 13. CARGO WORKSPACES
    # ═══════════════════════════════════════════════════════════
    ("rust/cargo-workspaces.md", "rust", ["pattern", "util"],
     "Cargo Workspaces",
     "Workspace [members], workspace dependencies, path deps, and feature propagation.",
     "pattern",
     """/*
=== FILE: Cargo.toml (workspace root) ===
[workspace]
members = [
    "crates/lib-core",
    "crates/cli",
    "crates/server",
]
resolver = "2"

# Shared dependencies (available to all members)
[workspace.dependencies]
serde = { version = "1", features = ["derive"] }
tokio = { version = "1", features = ["full"] }
anyhow = "1"

[workspace.package]
version = "0.1.0"
edition = "2021"
license = "MIT"

=== FILE: crates/lib-core/Cargo.toml ===
[package]
name = "lib-core"
version.workspace = true
edition.workspace = true

[dependencies]
serde.workspace = true
thiserror = "2"

=== FILE: crates/cli/Cargo.toml ===
[package]
name = "cli"
version.workspace = true
edition.workspace = true

[dependencies]
# Path dependency to sibling crate
lib-core = { path = "../lib-core" }
clap = { version = "4", features = ["derive"] }
anyhow.workspace = true
tokio.workspace = true

=== FILE: crates/server/Cargo.toml ===
[package]
name = "server"
version.workspace = true
edition.workspace = true

[dependencies]
lib-core = { path = "../lib-core" }
tokio.workspace = true
serde.workspace = true

[features]
default = ["lib-core/default"]
metrics = ["lib-core/metrics"]   # propagate feature to dep
*/
"""),

    # ═══════════════════════════════════════════════════════════
    # 14. FILE I/O
    # ═══════════════════════════════════════════════════════════
    ("rust/file-io.md", "rust", ["io", "file", "pattern"],
     "File I/O",
     "std::fs read/write/create_dir/remove, std::io::BufReader/BufWriter, and OpenOptions.",
     "pattern",
     """use std::fs;
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::Path;

fn main() -> io::Result<()> {
    // --- Write a file (overwrite) ---
    fs::write("hello.txt", "Hello, world!\n")?;
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
"""),

    # ═══════════════════════════════════════════════════════════
    # 15. LOGGING
    # ═══════════════════════════════════════════════════════════
    ("rust/logging.md", "rust", ["pattern", "util"],
     "Logging",
     "log crate with env_logger, tracing crate with spans, log levels, and structured fields.",
     "pattern",
     """// --- Setup (in main) ---
// With env_logger: RUST_LOG=info cargo run
// With tracing: RUST_LOG=info,my_crate=trace cargo run

use log::{info, warn, error, debug};
use tracing::{span, Level, instrument};

// --- Simple logging with log + env_logger ---
fn process_item(item: &str) {
    info!("Processing item: {item}");
    debug!("Item details: len={}", item.len());
    if item.is_empty() {
        warn!("Empty item encountered");
    }
}

fn read_config(path: &str) -> Result<String, std::io::Error> {
    info!("Reading config from {path}");
    let content = std::fs::read_to_string(path)?;
    Ok(content)
}

// --- Tracing with spans ---
#[instrument]   // auto-adds function name + args as span
fn compute_score(name: &str, value: i32) -> i32 {
    // Traced span created automatically
    let result = value * 2;
    tracing::info!(score = result, "Computed score");
    result
}

fn main() {
    // Initialize logger (call once at startup)
    env_logger::init();

    // --- log crate usage ---
    info!("Application started");
    process_item("hello");
    match read_config("config.toml") {
        Ok(cfg) => info!("Config loaded ({} bytes)", cfg.len()),
        Err(e) => error!("Failed to read config: {e}"),
    }

    // --- tracing span (manual) ---
    let parent_span = span!(Level::INFO, "request", id = 42);
    let _guard = parent_span.enter();
    tracing::info!("Processing request");
    compute_score("alice", 100);

    // --- Structured fields ---
    tracing::info!(
        user = "bob",
        action = "login",
        duration_ms = 45,
        "User logged in"
    );
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 16. FFI & UNSAFE
    # ═══════════════════════════════════════════════════════════
    ("rust/ffi-unsafe.md", "rust", ["pattern", "util"],
     "FFI & Unsafe",
     "extern \"C\", #[no_mangle], unsafe blocks, raw pointers, and std::ffi::CStr/CString.",
     "pattern",
     """use std::ffi::{CStr, CString};
use std::os::raw::c_char;

// --- Extern "C" function (callable from C/other langs) ---
#[no_mangle]
pub extern "C" fn rust_add(a: i32, b: i32) -> i32 {
    a + b
}

// --- FFI function that accepts a C string ---
#[no_mangle]
pub extern "C" fn rust_hello(name: *const c_char) -> *mut c_char {
    // SAFETY: caller guarantees name is a valid null-terminated C string
    let c_str = unsafe { CStr::from_ptr(name) };
    let rust_str = c_str.to_str().unwrap_or("world");
    let greeting = CString::new(format!("Hello, {rust_str}!")).unwrap();
    greeting.into_raw()    // transfer ownership to caller
}

// --- FFI function that frees a Rust-allocated string ---
#[no_mangle]
pub extern "C" fn rust_free_string(s: *mut c_char) {
    if !s.is_null() {
        // SAFETY: caller must pass a pointer returned by rust_hello
        unsafe { let _ = CString::from_raw(s); }
    }
}

// --- Calling C functions from Rust (example: strlen) ---
extern "C" {
    fn strlen(s: *const c_char) -> usize;
}

fn safe_strlen(s: &str) -> usize {
    let c_str = CString::new(s).expect("CString contains null byte");
    // SAFETY: c_str is a valid null-terminated string
    unsafe { strlen(c_str.as_ptr()) }
}

// --- Unsafe raw pointer dereference ---
fn unsafe_demo() {
    let mut x = 42u32;
    let raw_ptr: *mut u32 = &mut x;

    // SAFETY: raw_ptr points to valid, aligned memory
    unsafe {
        *raw_ptr = 100;
        println!("Raw pointer value: {raw_ptr} -> {}", *raw_ptr);
    }
}

fn main() {
    println!("rust_add(3, 4) = {}", rust_add(3, 4));
    println!("C strlen of 'hello': {}", safe_strlen("hello"));
    unsafe_demo();

    // Full cycle: call FFI function and free result
    let name = CString::new("Rust").unwrap();
    let ptr = rust_hello(name.as_ptr());
    let result = unsafe { CStr::from_ptr(ptr) }.to_str().unwrap().to_owned();
    rust_free_string(ptr);
    println!("FFI greeting: {result}");
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 17. MACROS
    # ═══════════════════════════════════════════════════════════
    ("rust/macros.md", "rust", ["pattern", "util"],
     "Declarative Macros",
     "macro_rules!, repetition patterns ($()), token types (expr, ident, ty), and helper attributes.",
     "pattern",
     """// --- Simple macro: map literals ---
macro_rules! hashmap {
    // Pattern: key => value, repeated
    ( $( $key:expr => $value:expr ),* $(,)? ) => {{
        let mut map = ::std::collections::HashMap::new();
        $(
            map.insert($key, $value);
        )*
        map
    }};
}

// --- Vec builder with optional separator ---
macro_rules! vec_strings {
    ( $( $x:expr ),+ $(,)? ) => {{
        let mut v = Vec::new();
        $(
            v.push(format!("{}", $x));
        )*
        v
    }};
}

// --- Macro that generates a function ---
macro_rules! create_getter {
    ($name:ident, $field:ident, $ty:ty) => {
        fn $name(&self) -> &$ty {
            &self.$field
        }
    };
}

struct User {
    name: String,
    age: u8,
}

impl User {
    create_getter!(get_name, name, String);
    create_getter!(get_age, age, u8);
}

// --- Helper attribute macro (declarative re-export) ---
macro_rules! with_retry {
    ($body:expr, $retries:expr) => {{
        let mut result = None;
        for attempt in 0..=$retries {
            match (|| $body)() {
                Ok(val) => { result = Some(val); break; }
                Err(e) if attempt < $retries => {
                    eprintln!("Attempt {} failed: {e}, retrying...", attempt + 1);
                }
                Err(e) => { return Err(e); }
            }
        }
        result.unwrap()
    }};
}

fn main() {
    // Use hashmap! macro
    let map = hashmap! {
        "alice" => 30,
        "bob" => 25,
    };
    println!("Macro map: {map:?}");

    // vec_strings! macro
    let v = vec_strings![100, 200, 300];
    println!("Vec strings: {v:?}");

    // Generated getters
    let user = User { name: "Charlie".into(), age: 35 };
    println!("Getter: name={}, age={}", user.get_name(), user.get_age());
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 18. CONST & STATIC
    # ═══════════════════════════════════════════════════════════
    ("rust/const-static.md", "rust", ["pattern", "util"],
     "Const & Static",
     "const vs static, const fn, associated constants, and lazy_static/once_cell::sync::OnceCell.",
     "pattern",
     """use std::sync::OnceLock;

// --- const (compile-time, inlined) ---
const MAX_RETRIES: u32 = 5;
const APP_NAME: &str = "myapp";

/// const fn — evaluated at compile time
const fn factorial(n: u32) -> u32 {
    let mut result = 1;
    let mut i = 1;
    while i <= n {
        result *= i;
        i += 1;
    }
    result
}

const FACT_10: u32 = factorial(10);

// --- static (single address, mutable requires unsafe) ---
static VERSION: &str = "1.0.0";
static mut COUNTER: u32 = 0;   // mutable static requires unsafe

// --- Associated constants on types ---
trait MathConstants {
    const PI: f64;
}

struct Circle;
impl MathConstants for Circle {
    const PI: f64 = 3.141592653589793;
}

// --- OnceLock (thread-safe lazy init, no alloc) ---
static CONFIG: OnceLock<String> = OnceLock::new();

fn get_config() -> &'static str {
    CONFIG.get_or_init(|| {
        // Expensive one-time initialization
        std::fs::read_to_string("config.toml").unwrap_or_default()
    })
}

fn main() {
    println!("App: {APP_NAME}, max retries: {MAX_RETRIES}");
    println!("Factorial(10) = {FACT_10}");
    println!("Version: {VERSION}");
    println!("PI = {}", Circle::PI);

    // OnceLock lazy init
    println!("Config: {}", get_config());

    // Mutable static (unsafe)
    unsafe {
        COUNTER += 1;
        println!("Counter: {COUNTER}");
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 19. NETWORKING
    # ═══════════════════════════════════════════════════════════
    ("rust/networking.md", "rust", ["net", "pattern", "async"],
     "Networking",
     "std::net::TcpListener/Stream, tokio::net, reqwest HTTP client, and URL parsing.",
     "pattern",
     """use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};

// --- Synchronous TCP echo server ---
fn handle_client(mut stream: TcpStream) {
    let peer = stream.peer_addr().unwrap();
    println!("New connection from {peer}");

    let mut reader = BufReader::new(&stream);
    let mut line = String::new();
    if reader.read_line(&mut line).is_ok() && !line.is_empty() {
        let _ = write!(stream, "Echo: {line}");
    }
    println!("Closed connection from {peer}");
}

fn std_tcp_server() {
    let listener = TcpListener::bind("127.0.0.1:7878").unwrap();
    println!("TCP server listening on :7878");

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => { handle_client(stream); }
            Err(e) => eprintln!("Connection failed: {e}"),
        }
    }
}

// --- Tokio TCP (async) ---
async fn tokio_tcp_server() {
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
    use tokio::net::TcpListener;

    let listener = TcpListener::bind("127.0.0.1:7879").await.unwrap();
    println!("Tokio TCP server on :7879");

    loop {
        let (mut stream, addr) = listener.accept().await.unwrap();
        println!("Tokio accepted: {addr}");

        tokio::spawn(async move {
            let mut reader = BufReader::new(&mut stream);
            let mut line = String::new();
            if reader.read_line(&mut line).await.is_ok() {
                let _ = stream.write_all(format!("Echo: {line}").as_bytes()).await;
            }
        });
    }
}

// --- Reqwest HTTP client ---
async fn http_client_demo() -> Result<(), reqwest::Error> {
    let client = reqwest::Client::new();

    // GET
    let resp = client.get("https://httpbin.org/get")
        .query(&[("name", "rust")])
        .send()
        .await?;
    println!("GET status: {}", resp.status());

    // POST JSON
    let body = serde_json::json!({"key": "value"});
    let resp = client.post("https://httpbin.org/post")
        .json(&body)
        .send()
        .await?;
    println!("POST status: {}", resp.status());

    Ok(())
}

// --- URL parsing ---
fn url_parse_demo() {
    let url = url::Url::parse("https://user:pass@example.com:8080/path?q=rust#section").unwrap();
    println!("Scheme: {}", url.scheme());
    println!("Host: {:?}", url.host());
    println!("Port: {:?}", url.port());
    println!("Path: {}", url.path());
    println!("Query: {:?}", url.query());
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 20. DOCUMENTATION
    # ═══════════════════════════════════════════════════════════
    ("rust/documentation.md", "rust", ["pattern", "util"],
     "Documentation",
     "//! inner doc (module level), /// outer doc, doc tests, cargo doc, and the #[doc] attribute.",
     "pattern",
     """//! # Rust Documentation Patterns
//!
//! This module demonstrates Rust documentation conventions.
//! Inner doc comments (`//!`) document the containing item (module, crate).
//!
//! Run `cargo doc --open` to see the rendered documentation.
//! Doc tests are run with `cargo test`.

/// Represents a 2D point in Cartesian coordinates.
///
/// # Examples
///
/// ```
/// use my_crate::Point;
///
/// let p = Point::new(3.0, 4.0);
/// assert_eq!(p.x(), 3.0);
/// ```
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Point {
    x: f64,
    y: f64,
}

impl Point {
    /// Create a new `Point`.
    ///
    /// # Arguments
    ///
    /// * `x` — The x-coordinate
    /// * `y` — The y-coordinate
    ///
    /// # Example
    ///
    /// ```
    /// let p = Point::new(1.0, 2.0);
    /// ```
    pub fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    /// Returns the x-coordinate.
    pub fn x(&self) -> f64 {
        self.x
    }

    /// Returns the y-coordinate.
    pub fn y(&self) -> f64 {
        self.y
    }

    /// Compute the distance between two points.
    ///
    /// This is a **doc test** that `cargo test` will run:
    ///
    /// ```
    /// use my_crate::Point;
    ///
    /// let a = Point::new(0.0, 0.0);
    /// let b = Point::new(3.0, 4.0);
    /// assert!((a.distance(&b) - 5.0).abs() < 1e-10);
    /// ```
    ///
    /// # Panics
    ///
    /// This method does not panic.
    pub fn distance(&self, other: &Point) -> f64 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        (dx * dx + dy * dy).sqrt()
    }
}

/// This test is hidden from the docs but still run by `cargo test`.
///
/// ```ignore
/// // This code is ignored during doc tests
/// ```
#[doc(hidden)]
pub fn internal_helper() -> i32 {
    42
}

/// The [`Point`] unit — see the [module-level docs](#).
///
/// You can also link to items: [`Point::new`], [`Point::distance`].
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_point() {
        let p = Point::new(1.0, 2.0);
        assert_eq!(p.x(), 1.0);
        assert_eq!(p.y(), 2.0);
    }

    #[test]
    fn test_distance() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(3.0, 4.0);
        assert!((a.distance(&b) - 5.0).abs() < 1e-10);
    }
}
"""),
]
