---
language: lua
tags: [file-io, io.open, read, write, io.lines, string.find, gmatch]
title: File I/O
description: Lua's io library provides File I/O: io.open returns a file handle. Read modes: "*a" (all), "*l" (line), "*n" (number). io.lines for line-by-line iteration. Useful with string.find/gmatch.
source: pattern
---

```lua
-- Write to file
local f = io.open("example.txt", "w")
if f then
  f:write("Line 1\n")
  f:write("Line 2\n")
  f:close()
end

-- Read entire file
local f = io.open("example.txt", "r")
if f then
  local content = f:read("*a")
  f:close()
  print(content)
end

-- Read line by line
local f = io.open("example.txt", "r")
if f then
  for line in f:lines() do
    print(">> " .. line)
  end
  f:close()
end

-- io.lines — open and iterate in one step
for line in io.lines("example.txt") do
  if string.find(line, "Line") then
    print("Found: " .. line)
  end
end

-- Pattern matching with data from file
local log = [[
2024-01-01 INFO  started
2024-01-01 ERROR disk full
2024-01-02 INFO  completed
]]

for line in string.gmatch(log, "[^\n]+") do
  local date, level, msg = string.match(line, "(%S+) (%S+) (.+)")
  if level == "ERROR" then
    print("ERROR on " .. date .. ": " .. msg)
  end
end

-- Append to file
local f = io.open("example.txt", "a")
if f then
  f:write("Appended line\n")
  f:close()
end
