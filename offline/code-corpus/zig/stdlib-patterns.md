---
language: zig
tags: [zig, stdlib, ArrayList, HashMap, sorting, formatting]
title: Standard Library Patterns
description: Common Zig stdlib usage — std.ArrayList, std.AutoHashMap, std.StringHashMap, sorting, formatting.
source: pattern
---

```zig
const std = @import("std");

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    // ── ArrayList ──
    var list = std.ArrayList(u32).init(allocator);
    try list.append(3);
    try list.append(1);
    try list.append(4);
    try list.append(1);
    try list.append(5);
    list.items[0] = 9;

    std.debug.print("list len={d}\n", .{list.items.len});

    // Sorting
    std.mem.sort(u32, list.items, {}, comptime std.sort.asc(u32));
    std.debug.print("sorted: {any}\n", .{list.items});

    // ── HashMap (AutoHashMap — key is value type) ──
    var map = std.AutoHashMap(u32, []const u8).init(allocator);
    try map.put(1, "one");
    try map.put(2, "two");
    try map.put(3, "three");

    const value = map.get(2) orelse "?";
    std.debug.print("key 2 -> {s}\n", .{value});

    // ── StringHashMap ──
    var str_map = std.StringHashMap(i32).init(allocator);
    try str_map.put("apple", 5);
    try str_map.put("banana", 3);
    try str_map.put("cherry", 8);

    const count = str_map.get("banana") orelse 0;
    std.debug.print("banana count = {d}\n", .{count});

    // ── Formatting ──
    var buf: [256]u8 = undefined;
    const line = try std.fmt.bufPrint(&buf, "value={d:0>4} hex=0x{X}", .{ 42, 255 });
    std.debug.print("{s}\n", .{line});

    // ── Iterator pattern ──
    var it = map.iterator();
    while (it.next()) |entry| {
        std.debug.print("  {d} -> {s}\n", .{ entry.key_ptr.*, entry.value_ptr.* });
    }
}

```
