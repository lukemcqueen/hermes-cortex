---
language: lua
tags: [c-api, ffi, luajit, lua_State, ffi.cdef, ffi.new, ffi.C]
title: C API & FFI
description: Lua's C API uses lua_State and stack-based operations. LuaJIT's FFI (ffi.cdef/ffi.new/ffi.C) allows direct C function calls and struct access from Lua, much faster than the C API.
source: pattern
---

```lua
-- =====================
-- LuaJIT FFI (preferred)
-- =====================
local ffi = require("ffi")

-- Declare C types and functions
ffi.cdef[[
  typedef struct { double x, y; } point_t;
  double sqrt(double x);
  int printf(const char *fmt, ...);
  int fact(int n);
]]

-- Load a shared library (if needed)
local mylib = ffi.load("mylib")

-- Use C structs
local p = ffi.new("point_t", {x = 3.0, y = 4.0})
print(p.x, p.y)  -- 3.0  4.0

-- Call C functions
local dist = ffi.C.sqrt(p.x * p.x + p.y * p.y)
print(dist)  -- 5.0

ffi.C.printf("distance = %f\n", dist)

-- Arrays
local arr = ffi.new("int[?]", 10, {1, 2, 3})
for i = 0, 9 do
  arr[i] = arr[i] + 1
end

```
