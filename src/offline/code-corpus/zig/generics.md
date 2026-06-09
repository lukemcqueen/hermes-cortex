---
language: zig
tags: [zig, generics, anytype, comptime-params, type-erasure]
title: Generic Types
description: Zig generic programming with anytype, @TypeOf, comptime parameters, generic structs, and type-erased containers.
source: pattern
---

```zig
const std = @import("std");

/// Generic function — accepts any type
fn identity(comptime T: type, value: T) T {
    return value;
}

/// Generic struct with a comptime parameter
fn Queue(comptime T: type) type {
    return struct {
        const Self = @This();
        items: []T,
        head: usize = 0,
        tail: usize = 0,

        fn init(allocator: std.mem.Allocator, capacity: usize) !Self {
            return Self{
                .items = try allocator.alloc(T, capacity),
            };
        }

        fn enqueue(self: *Self, value: T) void {
            self.items[self.tail] = value;
            self.tail += 1;
        }

        fn dequeue(self: *Self) ?T {
            if (self.head == self.tail) return null;
            defer self.head += 1;
            return self.items[self.head];
        }
    };
}

/// Type-erased any — store different types behind a union
const AnyValue = union(enum) {
    int: i64,
    float: f64,
    string: []const u8,
    none,
};

pub fn main() !void {
    // anytype — parameter inferred at call site
    const a = identity(u32, 42);
    const b = identity(f64, 3.14);
    const c = identity([]const u8, "hello");

    _ = a;
    _ = b;
    _ = c;

    // Generic queue of f64
    var queue = try Queue(f64).init(std.heap.page_allocator, 16);
    queue.enqueue(1.5);
    queue.enqueue(2.5);
    const val = queue.dequeue();
    if (val) |v| std.debug.print("dequeued: {d}
", .{v});

    // Type-erased values
    const v1 = AnyValue{ .int = 42 };
    const v2 = AnyValue{ .float = 2.71 };
    const v3 = AnyValue{ .string = "zig" };
    _ = .{ v1, v2, v3 };

    // @TypeOf at runtime
    std.debug.print("{s}
", .{@typeName(@TypeOf(val))}); // ?f64
}

```
