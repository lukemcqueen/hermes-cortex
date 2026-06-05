---
language: zig
tags: [zig, pointers, memory, allocator, heap]
title: Pointers & Memory
description: Zig pointer types (*T, [*]T), slice pointer, allocator pattern with alloc/free, and alignment.
source: pattern
---

```zig
const std = @import("std");

// Single-item pointer to T
fn increment(p: *u32) void {
    p.* += 1;
}

// Many-item pointer — unknown length, no sentinel
fn sum_slice(ptr: [*]const u8, len: usize) usize {
    var total: usize = 0;
    for (ptr[0..len]) |b| total += b;
    return total;
}

// Slice pointer — fat pointer (ptr + len)
fn double_each(slice: []f64) void {
    for (slice) |*v| v.* *= 2.0;
}

// Allocator pattern
pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    // Allocate a single u64 (aligned automatically)
    const p = try allocator.create(u64);
    p.* = 42;

    // Allocate a slice of 100 aligned floats
    const buf = try allocator.alloc(f64, 100);
    defer allocator.free(buf);
    @memset(buf, 3.14);
}

```
