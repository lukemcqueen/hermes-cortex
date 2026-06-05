---
language: lua
tags: [metatables, oop, setmetatable, __index, __call, __add, __tostring]
title: Metatables & OOP
description: Metatables control table behaviour via events (__index, __call, __add, __tostring, etc.). Use __index for prototype-based OOP — the classic Lua class pattern.
source: pattern
---

```lua
-- Metatable events
local t = {}
local mt = {
  __index = {greeting = "Hello"},         -- fallback lookup
  __newindex = function(t, k, v)          -- intercept writes
    print("Setting " .. k .. " = " .. tostring(v))
    rawset(t, k, v)
  end,
  __call = function(t, ...)               -- make table callable
    return "Called with " .. select("#", ...) .. " args"
  end,
  __tostring = function(t)
    local parts = {}
    for k, v in pairs(t) do
      table.insert(parts, k .. "=" .. tostring(v))
    end
    return "{" .. table.concat(parts, ", ") .. "}"
  end,
  __add = function(a, b)
    return setmetatable({x = a.x + b.x, y = a.y + b.y}, getmetatable(a))
  end,
}
setmetatable(t, mt)

-- Prototype-based OOP (class pattern)
local Animal = {}
Animal.__index = Animal

function Animal:new(name, sound)
  return setmetatable({name = name, sound = sound}, self)
end

function Animal:speak()
  print(self.name .. " says " .. self.sound)
end

local Dog = setmetatable({}, {__index = Animal})
Dog.__index = Dog

function Dog:new(name)
  return setmetatable({name = name, sound = "Woof!"}, self)
end

function Dog:fetch()
  print(self.name .. " fetches the stick")
end

local fido = Dog:new("Fido")
fido:speak()
fido:fetch()

```
