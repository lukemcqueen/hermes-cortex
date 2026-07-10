"""Zig (12) + Dart (15) snippet module — 27 entries total.

Zig snippets target Zig 0.13+; Dart snippets target Dart 3.x.
"""

SNIPPETS = [
    # ═══════════════════════════════════════════════════════════════
    # ZIG (12)
    # ═══════════════════════════════════════════════════════════════
    (
        "zig/pointers.md",
        "zig",
        ["zig", "pointers", "memory", "allocator", "heap"],
        "Pointers & Memory",
        "Zig pointer types (*T, [*]T), slice pointer, allocator pattern with alloc/free, and alignment.",
        "pattern",
        """```zig
const std = @import("std");

// Single-item pointer to T
fn increment(p: *u32) void {
    p.* += 1;
}

// Many-item pointer — unknown length, no sentinel
fn sum_slice(ptr: [*]const u8, len: usize) usize {
    var total: usize = 0;
    for (ptr[0..len]) |b| total += b;
    return total;
}

// Slice pointer — fat pointer (ptr + len)
fn double_each(slice: []f64) void {
    for (slice) |*v| v.* *= 2.0;
}

// Allocator pattern
pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    // Allocate a single u64 (aligned automatically)
    const p = try allocator.create(u64);
    p.* = 42;

    // Allocate a slice of 100 aligned floats
    const buf = try allocator.alloc(f64, 100);
    defer allocator.free(buf);
    @memset(buf, 3.14);
}
```""",
    ),
    (
        "zig/structs.md",
        "zig",
        ["zig", "structs", "methods", "oop", "packed", "backing"],
        "Structs & Methods",
        "Zig struct declaration, method syntax with self parameter, field defaults, backing bytes, and packed struct.",
        "pattern",
        """```zig
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
```""",
    ),
    (
        "zig/errors.md",
        "zig",
        ["zig", "errors", "error-union", "try", "catch", "errdefer", "anyerror"],
        "Error Handling",
        "Zig error unions (!), try/catch, errdefer for cleanup, error sets, and anyerror.",
        "pattern",
        """```zig
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
    std.debug.print("parsed: {d}\n", .{n});

    // catch — provide a default value
    const fallback = parse_u32("abc") catch 0;
    std.debug.print("fallback: {d}\n", .{fallback});

    // errdefer — runs on error path
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    errdefer arena.deinit(); // also free on error

    // Catch specific error
    const result = parse_u32("9999999999");
    if (result) |val| {
        std.debug.print("val={d}\n", .{val});
    } else |err| switch (err) {
        ParseError.Overflow => std.debug.print("overflow!\n", .{}),
        else => std.debug.print("other: {s}\n", .{@errorName(err)}),
    }
}
```""",
    ),
    (
        "zig/arrays-slices.md",
        "zig",
        ["zig", "arrays", "slices", "vectors", "concat", "simd"],
        "Arrays, Slices & Vectors",
        "Zig fixed-size arrays, slices ([]const T), concatenation (++), multislice, and SIMD vectors.",
        "pattern",
        """```zig
const std = @import("std");
const Vec4f = @Vector(4, f32);

pub fn main() !void {
    // Fixed-size array
    const arr = [5]u8{ 10, 20, 30, 40, 50 };
    std.debug.print("arr[2] = {d}\n", .{arr[2]});

    // Slice from array
    const slice: []const u8 = arr[1..4];
    std.debug.print("slice len={d}\n", .{slice.len}); // 3

    // Concatenation with ++
    const a = [_]u8{ 1, 2, 3 };
    const b = [_]u8{ 4, 5, 6 };
    const joined = a ++ b; // comptime-known
    std.debug.print("joined len={d}\n", .{joined.len}); // 6

    // Multislice / sentinel-terminated slice
    const cstr: [:0]const u8 = "hello zig";
    std.debug.print("cstr: {s}\n", .{cstr});

    // SIMD vector
    const va = Vec4f{ 1.0, 2.0, 3.0, 4.0 };
    const vb = Vec4f{ 5.0, 6.0, 7.0, 8.0 };
    const vc = va + vb;
    std.debug.print("vc = {d}\n", .{vc});
}
```""",
    ),
    (
        "zig/optionals-comptime.md",
        "zig",
        ["zig", "optionals", "comptime", "orelse", "typeinfo", "introspection"],
        "Optionals & Comptime",
        "Zig optional types (?T), orelse, unreachable, comptime introspection via @typeInfo.",
        "pattern",
        """```zig
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
    std.debug.print("val = {d}\n", .{val}); // 42

    // Unwrap with if
    if (maybe) |n| {
        std.debug.print("got: {d}\n", .{n});
    } else {
        std.debug.print("nothing\n", .{});
    }

    // unreachable — asserts this path is never hit
    const definitely: u32 = maybe orelse unreachable;

    // Comptime introspection
    std.debug.print("u32 is {s}\n", .{describe(u32)});
    std.debug.print("f64 is {s}\n", .{describe(f64)});

    // comptime block
    const len = comptime blk: {
        var sum: usize = 0;
        for ([_]u8{ 1, 2, 3, 4, 5 }) |v| sum += v;
        break :blk sum;
    };
    std.debug.print("comptime sum = {d}\n", .{len});
}
```""",
    ),
    (
        "zig/generics.md",
        "zig",
        ["zig", "generics", "anytype", "comptime-params", "type-erasure"],
        "Generic Types",
        "Zig generic programming with anytype, @TypeOf, comptime parameters, generic structs, and type-erased containers.",
        "pattern",
        """```zig
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
    if (val) |v| std.debug.print("dequeued: {d}\n", .{v});

    // Type-erased values
    const v1 = AnyValue{ .int = 42 };
    const v2 = AnyValue{ .float = 2.71 };
    const v3 = AnyValue{ .string = "zig" };
    _ = .{ v1, v2, v3 };

    // @TypeOf at runtime
    std.debug.print("{s}\n", .{@typeName(@TypeOf(val))}); // ?f64
}
```""",
    ),
    (
        "zig/file-io.md",
        "zig",
        ["zig", "file-io", "filesystem", "fs", "directory", "read-write"],
        "File I/O & Filesystem",
        "Zig std.fs — cwd(), openFile, readAll, close, stdout/stderr, and Dir methods.",
        "pattern",
        """```zig
const std = @import("std");

pub fn main() !void {
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    const allocator = arena.allocator();

    // Get current working directory
    const cwd = std.fs.cwd();

    // Write a file
    try cwd.writeFile2("hello.txt", "Hello from Zig!\\n", .{});

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
    std.debug.print("magic: 0x{X:0>8}\\n", .{magic});

    // stdout / stderr
    const stdout = std.io.getStdOut().writer();
    const stderr = std.io.getStdErr().writer();
    try stdout.print("stdout message\\n", .{});
    try stderr.print("stderr message\\n", .{});

    // Directory operations
    try cwd.makeDir("subdir");
    defer cwd.deleteDir("subdir") catch {};
    const subdir = try cwd.openDir("subdir", .{});
    try subdir.writeFile2("nested.txt", "nested\\n", .{});
}
```""",
    ),
    (
        "zig/build-system.md",
        "zig",
        ["zig", "build", "build.zig", "std.Build", "dependencies", "target"],
        "Zig Build System",
        "Zig build.zig with std.Build — executable, library, addCSourceFile, dependency resolution, and cross-compilation targets.",
        "pattern",
        """```zig
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
```""",
    ),
    (
        "zig/testing.md",
        "zig",
        ["zig", "testing", "test", "expect", "allocator", "test-runner"],
        "Testing",
        "Zig test blocks, expect/expectEqual, allocator testing, and test runner integration.",
        "pattern",
        """```zig
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
```""",
    ),
    (
        "zig/async-events.md",
        "zig",
        ["zig", "async", "await", "suspend", "resume", "event-loop", "non-blocking"],
        "Async & Events",
        "Zig async functions — async/await/suspend/resume, event loop polling, non-blocking I/O patterns.",
        "pattern",
        """```zig
const std = @import("std");

// Zig's async is stackful — each async function gets its own frame.

var pending_frame: ?anyframe = null;

fn async_worker() void {
    suspend {
        // Save the resumer so main can wake us later
        pending_frame = @frame();
    }
    // After resume
    std.debug.print("Worker resumed!\\n", .{});
}

pub fn main() !void {
    // Allocate a frame for the async function
    const frame = async async_worker();

    // At this point worker is suspended at the suspend point
    std.debug.print("Main: worker is suspended\\n", .{});

    // Resume it
    if (pending_frame) |f| resume f;

    // Wait for completion
    nosuspend await frame;
    std.debug.print("Main: worker finished\\n", .{});
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
```""",
    ),
    (
        "zig/c-interop.md",
        "zig",
        ["zig", "c-interop", "cImport", "cInclude", "extern", "ABI", "linkLib"],
        "C Interop & ABI",
        "Zig C interoperability — @cImport/@cInclude, extern struct, linkLib, @ptrCast, calling conventions.",
        "pattern",
        """```zig
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
    _ = c.printf("Hello from C interop!\\n");

    // Call math function
    const root = c.sqrt(144.0);
    std.debug.print("sqrt(144) = {d}\\n", .{root});

    // Call POSIX clock_gettime via extern
    var ts: timespec = undefined;
    const rc = clock_gettime(CLOCK_MONOTONIC, &ts);
    if (rc == 0) {
        std.debug.print("sec={d} nsec={d}\\n", .{ ts.tv_sec, ts.tv_nsec });
    }

    // @ptrCast — convert between pointer types
    const bytes: [*]const u8 = @ptrCast(&ts);
    std.debug.print("first byte: 0x{X:0>2}\\n", .{bytes[0]});

    // Calling convention annotations
    const Callback = *const fn (i32) callconv(.C) i32;
    fn native_callback(x: i32) callconv(.C) i32 {
        return x * 2;
    }
    const cb: Callback = native_callback;
    std.debug.print("callback(21) = {d}\\n", .{cb(21)});
}

// Link with a C library in build.zig:
// exe.linkLibC();
// exe.linkSystemLibrary("m");
```""",
    ),
    (
        "zig/stdlib-patterns.md",
        "zig",
        ["zig", "stdlib", "ArrayList", "HashMap", "sorting", "formatting"],
        "Standard Library Patterns",
        "Common Zig stdlib usage — std.ArrayList, std.AutoHashMap, std.StringHashMap, sorting, formatting.",
        "pattern",
        """```zig
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

    std.debug.print("list len={d}\\n", .{list.items.len});

    // Sorting
    std.mem.sort(u32, list.items, {}, comptime std.sort.asc(u32));
    std.debug.print("sorted: {any}\\n", .{list.items});

    // ── HashMap (AutoHashMap — key is value type) ──
    var map = std.AutoHashMap(u32, []const u8).init(allocator);
    try map.put(1, "one");
    try map.put(2, "two");
    try map.put(3, "three");

    const value = map.get(2) orelse "?";
    std.debug.print("key 2 -> {s}\\n", .{value});

    // ── StringHashMap ──
    var str_map = std.StringHashMap(i32).init(allocator);
    try str_map.put("apple", 5);
    try str_map.put("banana", 3);
    try str_map.put("cherry", 8);

    const count = str_map.get("banana") orelse 0;
    std.debug.print("banana count = {d}\\n", .{count});

    // ── Formatting ──
    var buf: [256]u8 = undefined;
    const line = try std.fmt.bufPrint(&buf, "value={d:0>4} hex=0x{X}", .{ 42, 255 });
    std.debug.print("{s}\\n", .{line});

    // ── Iterator pattern ──
    var it = map.iterator();
    while (it.next()) |entry| {
        std.debug.print("  {d} -> {s}\\n", .{ entry.key_ptr.*, entry.value_ptr.* });
    }
}
```""",
    ),
    # ═══════════════════════════════════════════════════════════════
    # DART (15)
    # ═══════════════════════════════════════════════════════════════
    (
        "dart/classes-oop.md",
        "dart",
        ["dart", "classes", "oop", "extends", "mixin", "abstract", "factory", "static"],
        "Classes & OOP",
        "Dart classes, constructors, extends, mixins, implements, abstract, factory, static, and late fields.",
        "pattern",
        """```dart
// ── Base class ──
abstract class Shape {
  double area();
  String describe() => 'Shape';
}

// ── Inheritance ──
class Circle extends Shape {
  final double radius;
  const Circle(this.radius);

  @override
  double area() => 3.14159 * radius * radius;

  @override
  String describe() => 'Circle(r=$radius)';
}

// ── Mixin ──
mixin Printable {
  void printInfo() => print('Info: $runtimeType');
}

mixin JsonSerializable on Shape {
  Map<String, dynamic> toJson();
}

// ── Using mixins ──
class Rectangle extends Shape with Printable, JsonSerializable {
  final double width, height;
  Rectangle(this.width, this.height);

  @override
  double area() => width * height;

  @override
  Map<String, dynamic> toJson() => {
    'type': 'rectangle',
    'width': width,
    'height': height,
  };
}

// ── Factory constructor ──
class Logger {
  static final Map<String, Logger> _cache = {};
  final String name;

  factory Logger(String name) {
    return _cache.putIfAbsent(name, () => Logger._internal(name));
  }

  Logger._internal(this.name);

  void log(String msg) => print('[$name] $msg');
}

// ── Static & late ──
class Config {
  static const String appName = 'DartApp';
  static int _counter = 0;

  late final List<int> data; // initialized later
  final int id;

  Config(this.data) : id = ++_counter;
}

void main() {
  final c = Circle(5);
  print('${c.describe()}: ${c.area()}');

  final r = Rectangle(3, 4);
  r.printInfo();
  print(r.toJson());

  final log1 = Logger('app');
  final log2 = Logger('app');
  print('Same instance: ${log1 == log2}'); // true
}
```""",
    ),
    (
        "dart/null-safety.md",
        "dart",
        ["dart", "null-safety", "nullable", "late", "required", "assertion"],
        "Null Safety",
        "Dart 3 null safety — !, ?, late, required, Object?, assertion, null-aware operators.",
        "pattern",
        """```dart
// ── Nullable types ──
String? maybeName(String? input) {
  return input?.toUpperCase(); // null-aware call
}

// ── Non-null assertion ──
int parseLenient(String? s) {
  // ! — asserts not null at runtime
  return s!.length;
}

// ── late — non-nullable but initialized later ──
class Database {
  late final List<String> records; // initialized before first use

  void load() {
    records = ['a', 'b', 'c'];
  }

  int get count => records.length;
}

// ── required named parameters ──
class Point {
  final double x, y;
  const Point({required this.x, required this.y});
}

// ── Object? — nullable root ──
void printType(Object? obj) {
  if (obj is int) {
    print('int: ${obj}');
  } else if (obj is String) {
    print('String: $obj');
  } else {
    print('unknown: $obj');
  }
}

// ── Null-aware operators ──
void nullAwareDemo() {
  String? a;
  String b = 'hello';

  // ?. — call only if non-null
  final len = a?.length;

  // ?? — provide default
  final name = a ?? 'default';

  // ??= — assign if null
  a ??= b;

  // Cascade with null-aware
  final list = <int>[];
  list
    ..add(1)
    ..add(2);

  // Assertion
  assert(a != null, 'a should not be null');
}

void main() {
  final db = Database();
  db.load();
  print('count: ${db.count}');
  print(maybeName('dart'));
  printType(42);
}
```""",
    ),
    (
        "dart/futures-streams.md",
        "dart",
        ["dart", "async", "future", "stream", "await", "async*", "yield"],
        "Futures & Streams",
        "Dart Future<T>, async/await, Stream<T>, listen, async* generators, yield, StreamController.",
        "pattern",
        """```dart
import 'dart:async';

// ── Future with async/await ──
Future<String> fetchData(String url) async {
  // Simulate network delay
  await Future.delayed(Duration(milliseconds: 100));
  return 'Data from $url';
}

// ── Stream with async* ──
Stream<int> countStream(int max) async* {
  for (var i = 1; i <= max; i++) {
    await Future.delayed(Duration(milliseconds: 50));
    yield i; // emit one value
  }
}

// ── StreamController (manual control) ──
Stream<int> createControlledStream() {
  final controller = StreamController<int>();
  var count = 0;

  Timer.periodic(Duration(milliseconds: 100), (timer) {
    count++;
    controller.add(count);
    if (count >= 5) {
      controller.close();
      timer.cancel();
    }
  });

  return controller.stream;
}

// ── Stream transformations ──
Stream<String> processStream(Stream<int> source) {
  return source
      .where((n) => n.isEven)
      .map((n) => 'Even: $n');
}

// ── Multiple await in a stream ──
Future<void> consumeStream(Stream<int> stream) async {
  await for (final value in stream) {
    print('Got: $value');
  }
}

void main() async {
  // Future
  final data = await fetchData('https://example.com');
  print(data);

  // Listen to stream
  final sub = countStream(3).listen(print);
  await Future.delayed(Duration(milliseconds: 200));
  sub.cancel();

  // Controlled stream
  final controlled = createControlledStream();
  await consumeStream(controlled);

  // Processed stream
  final processed = processStream(countStream(6));
  await consumeStream(processed);
}
```""",
    ),
    (
        "dart/collections.md",
        "dart",
        ["dart", "collections", "list", "set", "map", "spread", "cascade", "groupBy"],
        "Collections",
        "Dart List, Set, Map, spread (...), collection for/if, groupBy, cascade notation.",
        "pattern",
        """```dart
// ── List with collection-for and collection-if ──
List<int> buildList() {
  final numbers = [1, 2, 3, 4, 5];
  return [
    0,
    if (numbers.isNotEmpty) ...numbers,
    for (var i = 6; i <= 10; i++) i,
  ];
}

// ── Set ──
final uniqueNames = <String>{'alice', 'bob', 'alice', 'charlie'};
// → {'alice', 'bob', 'charlie'}

// ── Map operations ──
void mapDemo() {
  final scores = <String, int>{
    'alice': 95,
    'bob': 87,
    'charlie': 92,
  };

  // Spread
  final more = {'dave': 78, ...scores};

  // Map comprehension
  final doubled = scores.map((k, v) => MapEntry(k, v * 2));

  print('Alice: ${scores['alice']}');
  print('All: $more');
  print('Doubled: $doubled');
}

// ── groupBy (extension) ──
extension IterableGroupBy<T> on Iterable<T> {
  Map<K, List<T>> groupBy<K>(K Function(T) keyFn) {
    final map = <K, List<T>>{};
    for (final item in this) {
      final key = keyFn(item);
      map.putIfAbsent(key, () => []).add(item);
    }
    return map;
  }
}

// ── Cascade notation ──
List<int> cascadeDemo() {
  return <int>[]
    ..add(1)
    ..addAll([2, 3, 4])
    ..removeLast()
    ..insert(0, 0);
}

void main() {
  print(buildList()); // [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  print(uniqueNames); // {alice, bob, charlie}
  mapDemo();
  print([1, 1, 2, 2, 3].groupBy((n) => n.isEven ? 'even' : 'odd'));
  print(cascadeDemo()); // [0, 1, 2, 3]
}
```""",
    ),
    (
        "dart/flutter-widgets.md",
        "dart",
        ["dart", "flutter", "widgets", "material", "stateful", "stateless", "listview"],
        "Flutter Widgets",
        "Flutter Material Design widgets — StatelessWidget, StatefulWidget, MaterialApp, Scaffold, Column, Row, ListView.",
        "pattern",
        """```dart
import 'package:flutter/material.dart';

// ── StatelessWidget ──
class GreetingTile extends StatelessWidget {
  final String name;
  const GreetingTile({super.key, required this.name});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text('Hello, $name!', style: Theme.of(context).textTheme.headlineSmall),
      ),
    );
  }
}

// ── StatefulWidget ──
class CounterWidget extends StatefulWidget {
  const CounterWidget({super.key});
  @override
  State<CounterWidget> createState() => _CounterWidgetState();
}

class _CounterWidgetState extends State<CounterWidget> {
  int _count = 0;

  void _increment() => setState(() => _count++);

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Count: $_count', style: const TextStyle(fontSize: 24)),
        const SizedBox(height: 8),
        ElevatedButton(onPressed: _increment, child: const Text('+1')),
      ],
    );
  }
}

// ── App ──
class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const MyHomePage(),
    );
  }
}

class MyHomePage extends StatelessWidget {
  const MyHomePage({super.key});

  @override
  Widget build(BuildContext context) {
    final items = List.generate(20, (i) => 'Item $i');

    return Scaffold(
      appBar: AppBar(title: const Text('Flutter Widgets')),
      body: ListView.builder(
        itemCount: items.length,
        itemBuilder: (context, index) {
          return ListTile(
            leading: CircleAvatar(child: Text('${index + 1}')),
            title: Text(items[index]),
          );
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Pressed!')),
          );
        },
        child: const Icon(Icons.add),
      ),
    );
  }
}
```""",
    ),
    (
        "dart/functions-closures.md",
        "dart",
        ["dart", "functions", "closures", "lambda", "tear-off", "typedef", "higher-order"],
        "Functions & Closures",
        "Dart functions — anonymous functions, => syntax, tear-off, Function types, typedef, higher-order functions.",
        "pattern",
        """```dart
// ── typedef ──
typedef IntTransformer = int Function(int x);
typedef Comparator<T> = int Function(T a, T b);

// ── Higher-order function ──
List<int> transform(List<int> items, IntTransformer fn) {
  return items.map(fn).toList();
}

// ── Tear-off — using method reference ──
int triple(int x) => x * 3;

// ── Anonymous function / closure ──
Function makeMultiplier(int factor) {
  return (int x) => x * factor; // closure capturing 'factor'
}

// ── Function with positional & named params ──
String formatMessage(String msg, {String prefix = '>>', bool uppercase = false}) {
  var result = '$prefix $msg';
  return uppercase ? result.toUpperCase() : result;
}

// ── Records (Dart 3) ──
(String, int) lookup(String key) {
  // Simulated lookup returning a record
  return ('value for $key', 42);
}

void main() {
  // Tear-off
  final numbers = [1, 2, 3, 4, 5];
  final tripled = numbers.map(triple).toList();
  print(tripled); // [3, 6, 9, 12, 15]

  // Anonymous function
  final evens = numbers.where((n) => n.isEven).toList();
  print(evens); // [2, 4]

  // Closure
  final doubleIt = makeMultiplier(2);
  print(doubleIt(5)); // 10

  // Named parameters
  print(formatMessage('hello'));
  print(formatMessage('urgent', prefix: '!!!', uppercase: true));

  // Records
  final (val, code) = lookup('test');
  print('$val (code=$code)');

  // Function type variable
  IntTransformer combo = (x) => x * x + 1;
  print(combo(4)); // 17
}
```""",
    ),
    (
        "dart/json-serialization.md",
        "dart",
        ["dart", "json", "serialization", "fromJson", "toJson", "freezed", "dart-convert"],
        "JSON & Serialization",
        "Dart JSON handling — jsonDecode, jsonEncode, fromJson/toJson, freezed pattern, dart:convert.",
        "pattern",
        """```dart
import 'dart:convert';

// ── Manual JSON serialization ──
class User {
  final String name;
  final int age;
  final List<String> roles;

  const User({
    required this.name,
    required this.age,
    this.roles = const [],
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      name: json['name'] as String,
      age: json['age'] as int,
      roles: (json['roles'] as List<dynamic>?)?.cast<String>() ?? [],
    );
  }

  Map<String, dynamic> toJson() => {
    'name': name,
    'age': age,
    'roles': roles,
  };
}

// ── Freezed-like pattern using records (Dart 3) ──
// (Full freezed requires code-gen; this is a hand-written equivalent)
sealed class ApiResult<T> {
  const ApiResult();
}

class Success<T> extends ApiResult<T> {
  final T data;
  const Success(this.data);
}

class Failure<T> extends ApiResult<T> {
  final String message;
  final int? statusCode;
  const Failure(this.message, [this.statusCode]);
}

// ── JSON utilities ──
class JsonHelper {
  static String prettyEncode(Map<String, dynamic> data) {
    const encoder = JsonEncoder.withIndent('  ');
    return encoder.convert(data);
  }

  static T? safeDecode<T>(String json, T Function(Map<String, dynamic>) fromJson) {
    try {
      final map = jsonDecode(json) as Map<String, dynamic>;
      return fromJson(map);
    } catch (_) {
      return null;
    }
  }
}

void main() {
  // Encode
  final user = User(name: 'Alice', age: 30, roles: ['admin', 'editor']);
  final json = jsonEncode(user.toJson());
  print(json);

  // Decode
  final decoded = User.fromJson(jsonDecode(json) as Map<String, dynamic>);
  print('${decoded.name}, ${decoded.age}');

  // Pretty print
  print(JsonHelper.prettyEncode(user.toJson()));

  // Safe decode
  final parsed = JsonHelper.safeDecode('{"name":"Bob","age":25}', User.fromJson);
  print(parsed?.name);
}
```""",
    ),
    (
        "dart/error-handling.md",
        "dart",
        ["dart", "errors", "exceptions", "try", "catch", "finally", "rethrow"],
        "Error Handling",
        "Dart exception handling — try/on/catch/finally, rethrow, custom Exception classes, StackTrace.",
        "pattern",
        """```dart
// ── Custom exception ──
class ValidationException implements Exception {
  final String message;
  final String field;
  const ValidationException(this.message, this.field);

  @override
  String toString() => 'ValidationException($field): $message';
}

// ── Function that throws ──
int parseAge(String input) {
  final age = int.tryParse(input);
  if (age == null) {
    throw const FormatException('Invalid number');
  }
  if (age < 0 || age > 150) {
    throw ValidationException('Age out of range', 'age');
  }
  return age;
}

// ── Multiple catch clauses ──
void processAge(String input) {
  try {
    final age = parseAge(input);
    print('Age is $age');
  } on FormatException catch (e) {
    print('Format error: ${e.message}');
  } on ValidationException catch (e) {
    print('Validation error on ${e.field}: ${e.message}');
  } catch (e, stack) {
    // Generic catch with stack trace
    print('Unexpected error: $e');
    print('Stack: $stack');
  } finally {
    print('Finished processing age');
  }
}

// ── Rethrow pattern ──
void rethrowDemo(String input) {
  try {
    processAge(input);
  } catch (e) {
    // Log and rethrow
    print('[LOG] Error occurred: $e');
    rethrow; // preserves original stack trace
  }
}

// ── tryParse pattern (no exception) ──
int? safeParseAge(String input) {
  try {
    return parseAge(input);
  } on Exception {
    return null;
  }
}

// ── assert for internal invariants ──
int divide(int a, int b) {
  assert(b != 0, 'Division by zero');
  return a ~/ b;
}

void main() {
  processAge('25');  // OK
  processAge('abc'); // FormatException
  processAge('200'); // ValidationException

  print('Safe: ${safeParseAge('25')}');
  print('Safe: ${safeParseAge('invalid')}');
}
```""",
    ),
    (
        "dart/file-io-paths.md",
        "dart",
        ["dart", "file-io", "file", "directory", "paths", "dart-io", "path-provider"],
        "File I/O & Paths",
        "Dart dart:io — File, Directory, RandomAccessFile, path_provider, FileSystemEntity.",
        "pattern",
        """```dart
import 'dart:io';

// ── Write & read text file ──
Future<void> writeAndRead(String path) async {
  final file = File(path);

  // Write
  await file.writeAsString('Hello from Dart!\\nLine 2\\n');

  // Read entire file
  final content = await file.readAsString();
  print('Content:\\n$content');

  // Read as lines
  final lines = await file.readAsLines();
  print('Lines: $lines');
}

// ── Binary file ──
Future<void> writeBinary(String path) async {
  final file = File(path);
  final bytes = <int>[0xDE, 0xAD, 0xBE, 0xEF, 0x01, 0x02, 0x03, 0x04];
  await file.writeAsBytes(bytes);

  // RandomAccessFile for seeking
  final raf = await file.open(mode: FileMode.read);
  try {
    await raf.setPosition(2);
    final buf = await raf.read(4);
    print('Read at pos 2: ${buf.map((b) => b.toRadixString(16))}');
  } finally {
    await raf.close();
  }
}

// ── Directory operations ──
Future<void> directoryDemo(String dirPath) async {
  final dir = Directory(dirPath);

  // Create directory recursively
  if (!await dir.exists()) {
    await dir.create(recursive: true);
  }

  // List contents
  await for (final entity in dir.list(recursive: true, followLinks: false)) {
    final stat = await entity.stat();
    print('${entity.path} (${stat.type})');
  }

  // FileSystemEntity helpers
  final temp = Directory.systemTemp;
  print('Temp dir: ${temp.path}');
}

// ── path_provider (Flutter) ──
// In a Flutter project add path_provider package.
// import 'package:path_provider/path_provider.dart';
//
// Future<String> getAppDir() async {
//   final dir = await getApplicationDocumentsDirectory();
//   return dir.path;
// }

void main() async {
  await writeAndRead('example.txt');
  await writeBinary('example.bin');
  await directoryDemo('test_dir');

  // Cleanup
  await File('example.txt').delete();
  await File('example.bin').delete();
  await Directory('test_dir').delete(recursive: true);
}
```""",
    ),
    (
        "dart/isolates-concurrency.md",
        "dart",
        ["dart", "isolates", "concurrency", "Isolate", "send-port", "receive-port", "compute"],
        "Isolates & Concurrency",
        "Dart Isolate concurrency — Isolate.spawn, SendPort/ReceivePort, Flutter compute, Isolate.run.",
        "pattern",
        """```dart
import 'dart:async';
import 'dart:isolate';

// ── Worker function that receives a SendPort ──
void worker(SendPort sendPort) {
  sendPort.send('Hello from isolate!');
}

// ── Worker with request/response pattern ──
void calculator(SendPort sendPort) {
  final receivePort = ReceivePort();
  sendPort.send(receivePort.sendPort);

  receivePort.listen((message) {
    if (message is Map<String, dynamic>) {
      final a = message['a'] as int;
      final b = message['b'] as int;
      sendPort.send({'result': a + b});
    }
  });
}

// ── Heavy computation function (for Flutter compute) ──
int fibonacci(int n) {
  if (n <= 1) return n;
  return fibonacci(n - 1) + fibonacci(n - 2);
}

// ── Isolate.run (Dart 2.19+) ──
Future<int> runInIsolate(int n) async {
  return await Isolate.run(() => fibonacci(n));
}

// ── Complete Isolate lifecycle ──
Future<void> isolateDemo() async {
  // Simple spawn
  {
    final receivePort = ReceivePort();
    await Isolate.spawn(worker, receivePort.sendPort);
    final msg = await receivePort.first;
    print('Got: $msg');
  }

  // Request/response pattern
  {
    final receivePort = ReceivePort();
    final isolate = await Isolate.spawn(calculator, receivePort.sendPort);
    final workerSendPort = await receivePort.first as SendPort;

    final resultPort = ReceivePort();
    workerSendPort.send({'a': 10, 'b': 32});

    // Listen for results
    resultPort.listen((msg) {
      print('Result: $msg');
    });

    // Cleanup
    resultPort.close();
    isolate.kill(priority: Isolate.immediate);
  }

  // Isolate.run — simple
  {
    final result = await runInIsolate(40);
    print('fib(40) = $result');
  }
}

void main() async {
  await isolateDemo();
}
```""",
    ),
    (
        "dart/http-client.md",
        "dart",
        ["dart", "http", "client", "rest", "api", "json", "request"],
        "HTTP Client",
        "Dart HTTP — http package and dart:io HttpClient, GET/POST, headers, JSON response, error handling.",
        "pattern",
        """```dart
import 'dart:convert';
import 'dart:io';

// ── Using dart:io HttpClient ──
Future<Map<String, dynamic>> fetchViaHttpClient(String url) async {
  final client = HttpClient();
  try {
    final request = await client.getUrl(Uri.parse(url));
    request.headers.set('Accept', 'application/json');

    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();

    if (response.statusCode == 200) {
      return jsonDecode(body) as Map<String, dynamic>;
    } else {
      throw HttpException(
        'Request failed: ${response.statusCode}',
        uri: Uri.parse(url),
      );
    }
  } finally {
    client.close();
  }
}

// ── Using http package (pub.dev) ──
// Add dependency: dart pub add http
// import 'package:http/http.dart' as http;

Future<Map<String, dynamic>> fetchViaHttpPackage(String url) async {
  // final response = await http.get(Uri.parse(url));
  // if (response.statusCode == 200) {
  //   return jsonDecode(response.body) as Map<String, dynamic>;
  // }
  // throw Exception('Status: ${response.statusCode}');
  throw UnimplementedError('Add http package to use this');
}

// ── POST request ──
Future<Map<String, dynamic>> postJson(String url, Map<String, dynamic> data) async {
  final client = HttpClient();
  try {
    final request = await client.postUrl(Uri.parse(url));
    request.headers.contentType = ContentType.json;
    request.headers.set('Authorization', 'Bearer token123');
    request.write(jsonEncode(data));

    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();

    if (response.statusCode == 201 || response.statusCode == 200) {
      return jsonDecode(body) as Map<String, dynamic>;
    }
    throw HttpException('POST failed: ${response.statusCode}', uri: Uri.parse(url));
  } finally {
    client.close();
  }
}

// ── Response model ──
class ApiResponse {
  final int statusCode;
  final Map<String, dynamic>? data;
  final String? error;

  const ApiResponse({required this.statusCode, this.data, this.error});

  bool get isSuccess => statusCode >= 200 && statusCode < 300;
}

Future<ApiResponse> safeRequest(String url) async {
  try {
    return ApiResponse(statusCode: 200, data: await fetchViaHttpClient(url));
  } on SocketException catch (e) {
    return ApiResponse(statusCode: 0, error: 'Network error: $e');
  } on HttpException catch (e) {
    return ApiResponse(statusCode: -1, error: e.message);
  }
}

void main() async {
  // Example: fetchViaHttpClient('https://api.github.com/zen');
  // Example: postJson('https://httpbin.org/post', {'key': 'value'});

  // Safe request
  final result = await safeRequest('https://jsonplaceholder.typicode.com/todos/1');
  if (result.isSuccess) {
    print('Data: ${result.data}');
  } else {
    print('Error: ${result.error}');
  }
}
```""",
    ),
    (
        "dart/extensions-operators.md",
        "dart",
        ["dart", "extensions", "operators", "overloading", "callable", "custom-types"],
        "Extensions & Operators",
        "Dart extension methods on existing types, operator overloading, and callable classes.",
        "pattern",
        """```dart
// ── Extension on built-in type ──
extension IntSquared on int {
  int get squared => this * this;
  bool get isEven => this % 2 == 0;
}

// ── Extension on generic type ──
extension ListShuffle<T> on List<T> {
  List<T> shuffled() {
    final copy = [...this];
    copy.shuffle();
    return copy;
  }

  T? firstOrNull() => isEmpty ? null : first;
}

// ── Extension with operators ──
extension DurationMath on Duration {
  Duration operator *(int factor) => Duration(microseconds: inMicroseconds * factor);
  Duration operator +(Duration other) => Duration(microseconds: inMicroseconds + other.inMicroseconds);
}

// ── Operator overloading on custom class ──
class Vector2 {
  final double x, y;
  const Vector2(this.x, this.y);

  Vector2 operator +(Vector2 other) => Vector2(x + other.x, y + other.y);
  Vector2 operator -(Vector2 other) => Vector2(x - other.x, y - other.y);
  Vector2 operator *(double scalar) => Vector2(x * scalar, y * scalar);
  double operator [](int index) => index == 0 ? x : y;

  @override
  String toString() => 'Vector2($x, $y)';
}

// ── Callable class ──
class Multiplier {
  final int factor;
  const Multiplier(this.factor);

  int call(int value) => value * factor;
}

// ── Extension on enum ──
enum Status { pending, active, done }

extension StatusLabel on Status {
  String get label {
    return switch (this) {
      Status.pending => '⏳ Pending',
      Status.active => '✅ Active',
      Status.done => '✔ Completed',
    };
  }
}

void main() {
  print(5.squared); // 25
  print([1, 2, 3].shuffled());
  print([1, 2, 3].firstOrNull()); // 1
  print(<int>[].firstOrNull()); // null

  final v1 = Vector2(3, 4);
  final v2 = Vector2(1, 2);
  print(v1 + v2); // Vector2(4, 6)
  print(v1 * 2);   // Vector2(6, 8)
  print(v1[0]);    // 3.0

  final double = Multiplier(2);
  print(double(21)); // 42

  print(Status.pending.label);
  print(const Duration(seconds: 30) * 2); // 60 seconds
}
```""",
    ),
    (
        "dart/generics-type-system.md",
        "dart",
        ["dart", "generics", "type-system", "covariant", "typedef", "type-bounds"],
        "Generics & Type System",
        "Dart generics — generic classes/methods, type bounds (extends), covariant, typedef with generics.",
        "pattern",
        """```dart
// ── Generic class with type bound ──
class Box<T extends num> {
  final T value;
  const Box(this.value);

  Box<T> operator +(Box<T> other) => Box<T>((value + other.value) as T);
}

// ── Generic method ──
T firstOrElse<T>(List<T> items, T fallback) {
  return items.isNotEmpty ? items.first : fallback;
}

// ── Type bounds with interfaces ──
abstract class Jsonable {
  Map<String, dynamic> toJson();
}

class Repository<T extends Jsonable> {
  final List<T> _items = [];

  void add(T item) => _items.add(item);
  List<Map<String, dynamic>> exportAll() => _items.map((e) => e.toJson()).toList();
}

// ── covariant keyword ──
class Animal {
  void feed(covariant String food) => print('Fed $food');
}

class Dog extends Animal {
  @override
  void feed(String food) => print('Dog ate $food');
}

// ── typedef with generics ──
typedef Mapper<T, R> = R Function(T input);
typedef StreamTransformer<T> = Stream<T> Function(Stream<T> source);

// ── Using generics ──
void genericDemo() {
  final intBox = Box<int>(42);
  final result = intBox + Box<int>(8);
  print('Sum: ${result.value}'); // 50

  print(firstOrElse<String>([], 'default')); // default
  print(firstOrElse<int>([1, 2], -1));       // 1
}

// ── Type inference ──
var inferredList = [1, 2, 3]; // List<int>
final map = <String, dynamic>{'key': 'value'}; // explicit

// ── Multiple type parameters ──
class Pair<A, B> {
  final A first;
  final B second;
  const Pair(this.first, this.second);
}

void main() {
  genericDemo();

  final pair = Pair<String, int>('hello', 42);
  print('${pair.first}: ${pair.second}');

  final upperCase = const Mapper<String, String>((s) => s.toUpperCase());
  print(upperCase('hello'));
}
```""",
    ),
    (
        "dart/testing.md",
        "dart",
        ["dart", "testing", "test", "group", "expect", "mockito", "flutter-test", "setUp"],
        "Testing",
        "Dart testing with test package — test, group, expect, setUp, mockito, and flutter_test WidgetTester.",
        "pattern",
        """```dart
import 'package:test/test.dart';

// ── Functions to test ──
int add(int a, int b) => a + b;

Future<String> fetchGreeting(String name) async {
  await Future.delayed(const Duration(milliseconds: 10));
  return 'Hello, $name!';
}

// ── Basic tests ──
void main() {
  group('add()', () {
    test('returns sum of positive numbers', () {
      expect(add(2, 3), equals(5));
    });

    test('handles negative numbers', () {
      expect(add(-1, 1), equals(0));
      expect(add(-5, -3), equals(-8));
    });
  });

  group('fetchGreeting()', () {
    test('returns expected greeting', () async {
      final result = await fetchGreeting('Dart');
      expect(result, 'Hello, Dart!');
    });
  });

  // ── setUp / tearDown ──
  group('with setup', () {
    late List<int> data;

    setUp(() {
      data = [1, 2, 3, 4, 5];
    });

    tearDown(() {
      // cleanup if needed
    });

    test('data is populated', () {
      expect(data.length, 5);
    });

    test('data contains 3', () {
      expect(data, contains(3));
    });
  });

  // ── Matchers ──
  group('matchers', () {
    test('string matchers', () {
      expect('hello world', startsWith('hello'));
      expect('hello world', endsWith('world'));
      expect('hello world', contains('lo wo'));
    });

    test('collection matchers', () {
      expect([1, 2, 3], hasLength(3));
      expect([1, 2, 3], everyElement(isLessThan(10)));
      expect([1, 2, 3], unorderedEquals([3, 1, 2]));
    });

    test('throws matcher', () {
      expect(() => throw Exception('bad'), throwsException);
      expect(() => throw ArgumentError('nope'), throwsArgumentError);
    });
  });
}

// ── Mockito example ──
// Requires mockito package: dart pub add mockito
//
// class MockDatabase extends Mock implements Database {}
//
// void main() {
//   test('calls fetch', () {
//     final db = MockDatabase();
//     when(db.getUser(1)).thenReturn(User(id: 1, name: 'Alice'));
//     expect(db.getUser(1).name, 'Alice');
//   });
// }

// ── flutter_test WidgetTester ──
// Requires flutter_test package.
//
// void main() {
//   testWidgets('Counter increments', (tester) async {
//     await tester.pumpWidget(const CounterWidget());
//     expect(find.text('Count: 0'), findsOneWidget);
//     await tester.tap(find.byType(ElevatedButton));
//     await tester.pump();
//     expect(find.text('Count: 1'), findsOneWidget);
//   });
// }
```""",
    ),
    (
        "dart/riverpod-state-management.md",
        "dart",
        ["dart", "riverpod", "state-management", "provider", "ref", "flutter", "family", "autodispose"],
        "Riverpod / State Management",
        "Flutter Riverpod 2.x — Provider, StateNotifierProvider, ref.watch, ref.read, family, autodispose modifiers.",
        "pattern",
        """```dart
// Requires: flutter_riverpod, riverpod_annotation
// dart pub add flutter_riverpod riverpod_annotation
// dart pub add dev:riverpod_generator build_runner

import 'package:flutter_riverpod/flutter_riverpod.dart';

// ═══════════════════════════════════════════
// Simple Provider (sync value)
// ═══════════════════════════════════════════
final greetingProvider = Provider<String>((ref) {
  return 'Hello Riverpod!';
});

// ═══════════════════════════════════════════
// StateProvider (mutable simple state)
// ═══════════════════════════════════════════
final counterProvider = StateProvider<int>((ref) => 0);

// ═══════════════════════════════════════════
// FutureProvider (async data)
// ═══════════════════════════════════════════
final userProvider = FutureProvider<User>((ref) async {
  // Simulate network call
  await Future.delayed(const Duration(milliseconds: 200));
  return User(id: 1, name: 'Alice');
});

// ═══════════════════════════════════════════
// StateNotifierProvider (complex mutable state)
// ═══════════════════════════════════════════
class TodoListNotifier extends StateNotifier<List<Todo>> {
  TodoListNotifier() : super([]);

  void addTodo(String title) {
    state = [...state, Todo(id: state.length + 1, title: title)];
  }

  void toggleTodo(int id) {
    state = state.map((todo) {
      return todo.id == id ? todo.copyWith(done: !todo.done) : todo;
    }).toList();
  }

  void removeTodo(int id) {
    state = state.where((todo) => todo.id != id).toList();
  }
}

final todoListProvider = StateNotifierProvider<TodoListNotifier, List<Todo>>((ref) {
  return TodoListNotifier();
});

// ═══════════════════════════════════════════
// family — parameterized provider
// ═══════════════════════════════════════════
final todoDetailProvider = Provider.family<Todo?, int>((ref, id) {
  final todos = ref.watch(todoListProvider);
  return todos.where((t) => t.id == id).firstOrNull;
});

// ═══════════════════════════════════════════
// autodispose — cleanup when no longer watched
// ═══════════════════════════════════════════
final ephemeralProvider = FutureProvider.autoDispose<String>((ref) async {
  await Future.delayed(const Duration(seconds: 1));
  ref.onDispose(() => print('Disposed'));
  return 'Ephemeral';
});

// ═══════════════════════════════════════════
// Model classes
// ═══════════════════════════════════════════
class User {
  final int id;
  final String name;
  const User({required this.id, required this.name});
}

class Todo {
  final int id;
  final String title;
  final bool done;

  const Todo({required this.id, required this.title, this.done = false});

  Todo copyWith({int? id, String? title, bool? done}) {
    return Todo(
      id: id ?? this.id,
      title: title ?? this.title,
      done: done ?? this.done,
    );
  }
}

// ═══════════════════════════════════════════
// Widget usage (in Flutter)
// ═══════════════════════════════════════════
// class MyApp extends StatelessWidget {
//   @override
//   Widget build(BuildContext context) {
//     return ProviderScope(
//       child: MaterialApp(
//         home: Consumer(builder: (context, ref, _) {
//           final greeting = ref.watch(greetingProvider);
//           final counter = ref.watch(counterProvider);
//           return Scaffold(
//             body: Center(child: Text('$greeting Counter: $counter')),
//             floatingActionButton: FloatingActionButton(
//               onPressed: () => ref.read(counterProvider.notifier).state++,
//             ),
//           );
//         }),
//       ),
//     );
//   }
// }
```""",
    ),
]


# Deduplicate by rel_path (keep last occurrence)
def _deduplicate():
    seen = {}
    for i, entry in enumerate(SNIPPETS):
        seen[entry[0]] = i
    # Return deduplicated list preserving order of last occurrence
    indices = sorted(seen.values())
    return [SNIPPETS[i] for i in indices]


SNIPPETS = _deduplicate()
