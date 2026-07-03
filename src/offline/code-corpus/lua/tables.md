---
language: lua
tags: [tables, arrays, dictionaries, insert, remove, sort, pairs, ipairs]
title: Tables as Arrays/Dicts
description: Lua tables serve as both arrays and dictionaries. Use table.insert/remove/sort, # for length, pairs/ipairs for iteration. Table is the only data-structure.
source: pattern
---

```lua
-- Tables double as arrays (1-indexed) and dictionaries
local t = {10, 20, 30}          -- array part
t["key"] = "value"              -- dict part
t.speed = 100                   -- syntactic sugar for t["speed"]

-- Insert / Remove
table.insert(t, 40)             -- append
table.insert(t, 2, 15)          -- insert 15 at index 2
table.remove(t, 3)              -- remove element at index 3

-- Length (#) works on array-portion (contiguous integer keys)
print(#t)                       -- count of array-part

-- Iteration
for i, v in ipairs(t) do        -- ipairs: 1-indexed integer keys only
  print(i, v)
end

for k, v in pairs(t) do         -- pairs: all keys
  print(k, v)
end

-- Sort
local names = {"Charlie", "Alice", "Bob"}
table.sort(names)               -- alphabetical
table.sort(names, function(a, b) return #a < #b end)

-- Mixed usage
local inventory = {
  apples = 10,
  oranges = 5,
  {name = "sword", damage = 50},
  {name = "shield", defense = 30},
}
print(inventory.apples)          -- 10
print(inventory[1].name)         -- "sword"

```
