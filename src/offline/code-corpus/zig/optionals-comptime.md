---
language: zig
tags: [zig, optionals, comptime, orelse, typeinfo, introspection]
title: Optionals & Comptime
description: Zig optional types (?T), orelse, unreachable, comptime introspection via @typeInfo.
source: pattern
---

```zig
const std = @import("std");

/// Comptime function — resolves at compile time
fn describe(comptime T: type) []const u8 {
    return switch (@typeInfo(T)) {
        .Int => |info| switch (info.signedness) {
            .signed => "signed integer",
            .unsigned => "unsigned integer",
        },
        .Float => "float",
        .Struct => "struct",
        .Pointer => "pointer",
        else => "other",
    };
}

pub fn main() !void {
    // Optional (?T)
    const maybe: ?u32 = null;

    // orelse — provide fallback
    const val = maybe orelse 42;
    std.debug.print("val = {d}
", .{val}); // 42

    // Unwrap with if
    if (maybe) |n| {
        std.debug.print("got: {d}
", .{n});
    } else {
        std.debug.print("nothing
", .{});
    }

    // unreachable — asserts this path is never hit
    const definitely: u32 = maybe orelse unreachable;

    // Comptime introspection
    std.debug.print("u32 is {s}
", .{describe(u32)});
    std.debug.print("f64 is {s}
", .{describe(f64)});

    // comptime block
    const len = comptime blk: {
        var sum: usize = 0;
        for ([_]u8{ 1, 2, 3, 4, 5 }) |v| sum += v;
        break :blk sum;
    };
    std.debug.print("comptime sum = {d}
", .{len});
}

```
