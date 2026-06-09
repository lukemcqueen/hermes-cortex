---
language: lua
tags: [coroutines, coroutine.wrap, resume, yield, producer-consumer, coroutine.status]
title: Coroutines
description: Coroutines provide cooperative multitasking. coroutine.create/resume/yield. coroutine.wrap returns a callable wrapper. Use for generators, producer-consumer, state machines.
source: pattern
---

```lua
-- Basic coroutine
local co = coroutine.create(function()
  print("coroutine started")
  local val = coroutine.yield("first yield")
  print("received: " .. val)
  return "done"
end)

local status, result = coroutine.resume(co)
print("main got: " .. result)

status, result = coroutine.resume(co, "hello from main")
print("main got: " .. result)

print("status: " .. coroutine.status(co))  -- "dead"

-- coroutine.wrap (simpler, no status returned)
local wrap = coroutine.wrap(function()
  for i = 1, 5 do
    coroutine.yield(i * 2)
  end
end)

for _ = 1, 5 do
  print(wrap())  -- 2, 4, 6, 8, 10
end

-- Producer-Consumer pattern
function producer(consumer)
  return coroutine.wrap(function()
    for i = 1, 5 do
      print("producing " .. i)
      consumer(i)
    end
  end)
end

function consumer()
  return coroutine.create(function()
    while true do
      local _, value = coroutine.yield()
      print("consuming " .. value)
    end
  end)
end

-- Filter coroutine (pipeline)
function filter(source, predicate)
  return coroutine.wrap(function()
    for value in source do
      if predicate(value) then
        coroutine.yield(value)
      end
    end
  end)
end

local numbers = coroutine.wrap(function()
  for i = 1, 10 do coroutine.yield(i) end
end)

local evens = filter(numbers, function(n) return n % 2 == 0 end)
for n in evens do
  print(n)  -- 2, 4, 6, 8, 10
end

```
