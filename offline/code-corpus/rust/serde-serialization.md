---
language: rust
tags: [pattern, io]
title: Serde Serialization
description: serde::{Serialize, Deserialize}, #[serde(rename)], json::to_string/from_str, and custom serde.
source: pattern
---

```rust
use serde::{Deserialize, Serialize};
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
    println!("Serialized:
{json}");

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

```
