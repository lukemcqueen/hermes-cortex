---
language: zig
tags: [zig, structs, methods, oop, packed, backing]
title: Structs & Methods
description: Zig struct declaration, method syntax with self parameter, field defaults, backing bytes, and packed struct.
source: pattern
---

```zig
const std = @import("std");

const Vec3 = struct {
    x: f64 = 0.0,
    y: f64 = 0.0,
    z: f64 = 0.0,

    // Method — first parameter is the receiver
    fn length(self: Vec3) f64 {
        return @sqrt(self.x * self.x + self.y * self.y + self.z * self.z);
    }

    fn normalize(self: *Vec3) void {
        const inv_len = 1.0 / self.length();
        self.x *= inv_len;
        self.y *= inv_len;
        self.z *= inv_len;
    }
};

// Packed struct — bit-level layout, useful for protocols
const Flags = packed struct(u32) {
    ready: bool = false,
    error: bool = false,
    kind: u3 = 0,
    reserved: u27 = 0,
};

// Backing struct — integer repr via @bitCast
const Rgb = struct {
    r: u8,
    g: u8,
    b: u8,
};

test "struct basics" {
    const v = Vec3{ .x = 1.0, .y = 2.0, .z = 2.0 };
    try std.testing.expectEqual(@as(f64, 3.0), v.length());

    var flags = Flags{};
    flags.ready = true;
    flags.kind = 5;
    const raw: u32 = @bitCast(flags);
    try std.testing.expect(raw & 1 == 1); // bit 0 = ready

    const color = Rgb{ .r = 0xFF, .g = 0x80, .b = 0x00 };
    const packed: u32 = @bitCast(color);
    try std.testing.expectEqual(@as(u32, 0x0080FF), packed);
}

```
