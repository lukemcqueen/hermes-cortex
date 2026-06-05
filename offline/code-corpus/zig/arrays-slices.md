---
language: zig
tags: [zig, arrays, slices, vectors, concat, simd]
title: Arrays, Slices & Vectors
description: Zig fixed-size arrays, slices ([]const T), concatenation (++), multislice, and SIMD vectors.
source: pattern
---

```zig
const std = @import("std");
const Vec4f = @Vector(4, f32);

pub fn main() !void {
    // Fixed-size array
    const arr = [5]u8{ 10, 20, 30, 40, 50 };
    std.debug.print("arr[2] = {d}
", .{arr[2]});

    // Slice from array
    const slice: []const u8 = arr[1..4];
    std.debug.print("slice len={d}
", .{slice.len}); // 3

    // Concatenation with ++
    const a = [_]u8{ 1, 2, 3 };
    const b = [_]u8{ 4, 5, 6 };
    const joined = a ++ b; // comptime-known
    std.debug.print("joined len={d}
", .{joined.len}); // 6

    // Multislice / sentinel-terminated slice
    const cstr: [:0]const u8 = "hello zig";
    std.debug.print("cstr: {s}
", .{cstr});

    // SIMD vector
    const va = Vec4f{ 1.0, 2.0, 3.0, 4.0 };
    const vb = Vec4f{ 5.0, 6.0, 7.0, 8.0 };
    const vc = va + vb;
    std.debug.print("vc = {d}
", .{vc});
}

```
