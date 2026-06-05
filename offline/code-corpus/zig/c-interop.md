---
language: zig
tags: [zig, c-interop, cImport, cInclude, extern, ABI, linkLib]
title: C Interop & ABI
description: Zig C interoperability — @cImport/@cInclude, extern struct, linkLib, @ptrCast, calling conventions.
source: pattern
---

```zig
const std = @import("std");

// Import C headers
const c = @cImport({
    @cInclude("stdio.h");
    @cInclude("math.h");
});

// Extern struct — matches C struct layout
const timespec = extern struct {
    tv_sec: i64,
    tv_nsec: i64,
};

// Extern function declaration
extern "c" fn clock_gettime(clk_id: c_int, tp: *timespec) c_int;

const CLOCK_MONOTONIC: c_int = 1;

pub fn main() !void {
    // Call C printf
    _ = c.printf("Hello from C interop!\n");

    // Call math function
    const root = c.sqrt(144.0);
    std.debug.print("sqrt(144) = {d}\n", .{root});

    // Call POSIX clock_gettime via extern
    var ts: timespec = undefined;
    const rc = clock_gettime(CLOCK_MONOTONIC, &ts);
    if (rc == 0) {
        std.debug.print("sec={d} nsec={d}\n", .{ ts.tv_sec, ts.tv_nsec });
    }

    // @ptrCast — convert between pointer types
    const bytes: [*]const u8 = @ptrCast(&ts);
    std.debug.print("first byte: 0x{X:0>2}\n", .{bytes[0]});

    // Calling convention annotations
    const Callback = *const fn (i32) callconv(.C) i32;
    fn native_callback(x: i32) callconv(.C) i32 {
        return x * 2;
    }
    const cb: Callback = native_callback;
    std.debug.print("callback(21) = {d}\n", .{cb(21)});
}

// Link with a C library in build.zig:
// exe.linkLibC();
// exe.linkSystemLibrary("m");

```
