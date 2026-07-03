---
language: lua
tags: [error-handling, pcall, xpcall, error, assert, debug.traceback, protected-calls]
title: Error Handling & pcall
description: pcall (protected call) catches runtime errors without crashing. xpcall adds an error handler. error() raises an error, assert() as validation. debug.traceback provides stack traces.
source: pattern
---

```lua
-- pcall — protected call, returns status + results
local function risky(n)
  if n == 0 then
    error("cannot divide by zero!")
  end
  return 100 / n
end

local ok, result = pcall(risky, 5)
if ok then
  print("success:", result)    -- 20
else
  print("error:", result)
end

local ok, err = pcall(risky, 0)
print(ok, err)  -- false, "cannot divide by zero!"

-- xpcall — protected call with error handler
local function error_handler(err)
  print("caught:", err)
  print(debug.traceback())
  return "handled: " .. err
end

local ok, result = xpcall(risky, error_handler, 0)
print(ok, result)

-- assert — raises error if condition is false
local file = assert(io.open("nonexistent.txt", "r"), "file not found")

-- Custom assert style
local function ensure(cond, msg)
  if not cond then
    error(msg or "assertion failed", 2)
  end
end

-- Multiple return values from pcall
local function read_safe(path)
  local f, err = io.open(path, "r")
  if not f then return nil, err end
  local content = f:read("*a")
  f:close()
  return content
end

local ok, content_or_err = pcall(read_safe, "config.lua")
if ok then
  print(content_or_err)
else
  io.stderr:write("error: " .. content_or_err .. "\n")
end

```
