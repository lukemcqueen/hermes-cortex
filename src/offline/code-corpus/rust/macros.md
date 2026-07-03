---
language: rust
tags: [pattern, util]
title: Declarative Macros
description: macro_rules!, repetition patterns ($()), token types (expr, ident, ty), and helper attributes.
source: pattern
---

```rust
// --- Simple macro: map literals ---
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

```
