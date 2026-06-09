---
language: lua
tags: [functions, closures, upvalues, variadic, tail-calls, coroutines]
title: Functions & Closures
description: Lua has first-class functions with lexical scoping. Closures capture upvalues. Variadic ... arguments. Tail calls reuse stack frame. Coroutines for cooperative multitasking.
source: pattern
---

```lua
-- First-class function assigned to variable
local greet = function(name)
  return "Hello, " .. name
end
print(greet("Lua"))  -- "Hello, Lua"

-- Closure capturing an upvalue
function make_counter(start)
  local count = start
  return function()
    count = count + 1
    return count
  end
end

local counter = make_counter(10)
print(counter())  -- 11
print(counter())  -- 12

-- Variadic function (arbitrary arguments)
function sum(...)
  local total = 0
  for _, v in ipairs({...}) do
    total = total + v
  end
  return total
end
print(sum(1, 2, 3, 4, 5))  -- 15

-- Named + variadic with select
function printf(fmt, ...)
  local args = {...}
  for i = 1, select("#", ...) do end
  print(string.format(fmt, ...))
end

-- Tail call (no extra stack frame)
function factorial(n, acc)
  acc = acc or 1
  if n <= 1 then return acc end
  return factorial(n - 1, n * acc)  -- tail call
end
print(factorial(5))  -- 120

-- Coroutine as closure-based generator
function range_gen(limit)
  return coroutine.wrap(function()
    for i = 1, limit do
      coroutine.yield(i)
    end
  end)
end

local gen = range_gen(3)
print(gen())  -- 1
print(gen())  -- 2
print(gen())  -- 3
print(gen())  -- nil (done)

```
