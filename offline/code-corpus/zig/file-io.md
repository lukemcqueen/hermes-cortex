---
language: zig
tags: [zig, file-io, filesystem, fs, directory, read-write]
title: File I/O & Filesystem
description: Zig std.fs — cwd(), openFile, readAll, close, stdout/stderr, and Dir methods.
source: pattern
---

```zig
const std = @import("std");

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    // Get current working directory
    const cwd = std.fs.cwd();

    // Write a file
    try cwd.writeFile2("hello.txt", "Hello from Zig!\n", .{});

    // Read the entire file
    const content = try cwd.readFileAlloc(allocator, "hello.txt", 1024);
    defer allocator.free(content);
    std.debug.print("Read: {s}", .{content});

    // Open file for fine-grained control
    const file = try cwd.createFile("data.bin", .{});
    defer file.close();

    // Write structured data
    const writer = file.writer();
    try writer.writeInt(u32, 0xDEADBEEF, .big);
    try writer.writeAll(&[_]u8{ 1, 2, 3, 4 });

    // Read back
    try file.seekTo(0);
    const reader = file.reader();
    const magic = try reader.readInt(u32, .big);
    std.debug.print("magic: 0x{X:0>8}\n", .{magic});

    // stdout / stderr
    const stdout = std.io.getStdOut().writer();
    const stderr = std.io.getStdErr().writer();
    try stdout.print("stdout message\n", .{});
    try stderr.print("stderr message\n", .{});

    // Directory operations
    try cwd.makeDir("subdir");
    defer cwd.deleteDir("subdir") catch {};
    const subdir = try cwd.openDir("subdir", .{});
    try subdir.writeFile2("nested.txt", "nested\n", .{});
}

```
