---
language: zig
tags: [zig, async, await, suspend, resume, event-loop, non-blocking]
title: Async & Events
description: Zig async functions — async/await/suspend/resume, event loop polling, non-blocking I/O patterns.
source: pattern
---

```zig
const std = @import("std");

// Zig's async is stackful — each async function gets its own frame.

var pending_frame: ?anyframe = null;

fn async_worker() void {
    suspend {
        // Save the resumer so main can wake us later
        pending_frame = @frame();
    }
    // After resume
    std.debug.print("Worker resumed!\n", .{});
}

pub fn main() !void {
    // Allocate a frame for the async function
    const frame = async async_worker();

    // At this point worker is suspended at the suspend point
    std.debug.print("Main: worker is suspended\n", .{});

    // Resume it
    if (pending_frame) |f| resume f;

    // Wait for completion
    nosuspend await frame;
    std.debug.print("Main: worker finished\n", .{});
}

// --- Event loop / non-blocking I/O ---
// (Conceptual — full event-loop is typically provided by a framework)

const Reader = struct {
    fd: std.os.fd_t,
    buf: []u8,
    frame: ?anyframe = null,

    fn read(self: *Reader) usize {
        // In a real event loop you'd register with epoll/kqueue
        // and suspend until data is available.
        suspend {
            self.frame = @frame();
            // os.poll or similar registration happens here
        }
        const n = std.os.read(self.fd, self.buf) catch 0;
        return n;
    }
};

test "async frame lifecycle" {
    const T = struct {
        fn task() void {
            suspend {}
        }
    };
    var frame = async T.task();
    // Frame is now suspended
    resume frame;
    nosuspend await frame;
}

```
