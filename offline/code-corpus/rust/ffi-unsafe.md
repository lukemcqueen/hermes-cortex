---
language: rust
tags: [pattern, util]
title: FFI & Unsafe
description: extern "C", #[no_mangle], unsafe blocks, raw pointers, and std::ffi::CStr/CString.
source: pattern
---

```rust
use std::ffi::{CStr, CString};
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

```
