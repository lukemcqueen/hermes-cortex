---
language: zig
tags: [zig, testing, test, expect, allocator, test-runner]
title: Testing
description: Zig test blocks, expect/expectEqual, allocator testing, and test runner integration.
source: pattern
---

```zig
const std = @import("std");
const testing = std.testing;

/// Function under test
fn add(a: i32, b: i32) i32 {
    return a + b;
}

/// Function that allocates
fn duplicate(allocator: std.mem.Allocator, s: []const u8) ![]u8 {
    const copy = try allocator.dupe(u8, s);
    return copy;
}

test "basic addition" {
    try testing.expect(add(2, 2) == 4);
    try testing.expectEqual(@as(i32, 0), add(-1, 1));
}

test "equality with expectEqual" {
    const result = [_]u8{ 1, 2, 3 };
    const expected = [_]u8{ 1, 2, 3 };
    try testing.expectEqualSlices(u8, &expected, &result);
}

test "allocator testing" {
    // testing.allocator detects leaks and double-frees
    const allocator = testing.allocator;
    const copy = try duplicate(allocator, "hello, world!");
    defer allocator.free(copy);
    try testing.expectEqualSlices(u8, "hello, world!", copy);
}

test "error set inference" {
    const FileError = error{ NotFound, PermissionDenied };

    fn may_fail(code: u8) FileError!void {
        switch (code) {
            0 => return FileError.NotFound,
            1 => return FileError.PermissionDenied,
            else => return,
        }
    }

    try testing.expectError(FileError.NotFound, may_fail(0));
    try testing.expectError(FileError.PermissionDenied, may_fail(1));
    try may_fail(2); // no error
}

// Run with: zig test src/main.zig
// Or: zig build test

```
