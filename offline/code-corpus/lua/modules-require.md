---
language: lua
tags: [modules, require, package.path, return-table, local-functions, module-pattern]
title: Modules & require
description: Lua modules are files returning a table. require caches loaded modules. package.path controls search locations. Local functions hide internal details; only exported ones go in the return table.
source: pattern
---

```lua
-- mylib.lua
-- Local (private) functions
local function private_helper(x)
  return x * 2
end

-- Public functions returned in the module table
local mylib = {}

function mylib.greet(name)
  return "Hello, " .. name
end

function mylib.double(n)
  return private_helper(n)
end

function mylib.process_list(t)
  local result = {}
  for _, v in ipairs(t) do
    table.insert(result, private_helper(v))
  end
  return result
end

mylib.version = "1.0.0"

return mylib

```
