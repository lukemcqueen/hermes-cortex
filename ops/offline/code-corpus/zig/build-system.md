---
language: zig
tags: [zig, build, build.zig, std.Build, dependencies, target]
title: Zig Build System
description: Zig build.zig with std.Build — executable, library, addCSourceFile, dependency resolution, and cross-compilation targets.
source: pattern
---

```zig
const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    // Main executable
    const exe = b.addExecutable(.{
        .name = "my-app",
        .root_source_file = b.path("src/main.zig"),
        .target = target,
        .optimize = optimize,
    });

    // Add C source file for interop
    exe.addCSourceFile(.{
        .file = b.path("src/helper.c"),
        .flags = &[_][]const u8{"-Wall", "-O2"},
    });
    exe.linkLibC();

    // Link a system library
    exe.linkSystemLibrary("z");

    // Static library
    const lib = b.addStaticLibrary(.{
        .name = "mylib",
        .root_source_file = b.path("src/lib.zig"),
        .target = target,
        .optimize = optimize,
    });
    b.installArtifact(lib);

    // Unit tests
    const main_tests = b.addTest(.{
        .root_source_file = b.path("src/main.zig"),
        .target = target,
        .optimize = optimize,
    });
    const test_run = b.addRunArtifact(main_tests);
    test_run.has_side_effects = true;

    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&test_run.step);

    // Install
    b.installArtifact(exe);

    // Run command
    const run_cmd = b.addRunArtifact(exe);
    run_cmd.step.dependOn(b.getInstallStep());
    const run_step = b.step("run", "Run the app");
    run_step.dependOn(&run_cmd.step);
}

```
