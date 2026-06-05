---
language: zig
tags: [zig, errors, error-union, try, catch, errdefer, anyerror]
title: Error Handling
description: Zig error unions (!), try/catch, errdefer for cleanup, error sets, and anyerror.
source: pattern
---

```zig
const std = @import("std");

// Declare an error set
const ParseError = error{
    InvalidChar,
    Overflow,
    UnexpectedEnd,
};

// Returns an error union
fn parse_u32(buf: []const u8) ParseError!u32 {
    if (buf.len == 0) return ParseError.UnexpectedEnd;
    var value: u32 = 0;
    for (buf) |ch| {
        if (ch < '0' or ch > '9') return ParseError.InvalidChar;
        const digit = ch - '0';
        // Overflow check
        if (value > (std.math.maxInt(u32) - digit) / 10)
            return ParseError.Overflow;
        value = value * 10 + digit;
    }
    return value;
}

pub fn main() !void {
    // try — propagates error up the call stack
    const n = try parse_u32("12345");
    std.debug.print("parsed: {d}
", .{n});

    // catch — provide a default value
    const fallback = parse_u32("abc") catch 0;
    std.debug.print("fallback: {d}
", .{fallback});

    // errdefer — runs on error path
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    errdefer arena.deinit(); // also free on error

    // Catch specific error
    const result = parse_u32("9999999999");
    if (result) |val| {
        std.debug.print("val={d}
", .{val});
    } else |err| switch (err) {
        ParseError.Overflow => std.debug.print("overflow!
", .{}),
        else => std.debug.print("other: {s}
", .{@errorName(err)}),
    }
}

```
