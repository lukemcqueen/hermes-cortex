---
language: lua
tags: [strings, patterns, match, gmatch, gsub, captures, string-library]
title: Lua Patterns & Strings
description: Lua has a lightweight pattern language (not full regex). string.match/gmatch/gsub/sub/upper/lower/rep/format. Captures with (). Character classes: %d, %a, %s, etc.
source: pattern
---

```lua
-- String basics
local s = "  Hello, Lua!  "
print(string.len(s))          -- 15
print(string.upper(s))        -- "  HELLO, LUA!  "
print(string.lower(s))        -- "  hello, lua!  "
print(string.sub(s, 3, 7))    -- "Hello"
print(string.rep("Ha", 3))    -- "HaHaHa"
print(string.format("\u03c0 \u2248 %.3f", math.pi))  -- "\u03c0 \u2248 3.142"

-- Patterns (not regex)
local text = "hello 123 world 456"

-- string.find returns start, end indices
local s, e = string.find(text, "%d+")
print(s, e)  -- 7, 9 ("123")

-- string.match returns first capture or full match
local num = string.match(text, "(%d+)")
print(num)  -- "123"

-- string.gmatch iterates all matches
for n in string.gmatch(text, "(%d+)") do
  print(n)
end

-- string.gsub replaces globally
local result, count = string.gsub("one, two, one", "one", "1")
print(result)  -- "1, two, 1"
print(count)   -- 2

-- Captures in patterns
local email = "user@example.com"
local name, domain = string.match(email, "([^@]+)@(.+)")
print(name, domain)  -- "user"  "example.com"

-- Character classes: %d (digit), %a (letter), %s (space), %w (alnum), %p (punct)
local csv = "a,b,c,d"
for field in string.gmatch(csv, "([^,]+)") do
  print(field)
end

```
