---
language: lua
tags: [luarocks, install, rockspec, dependencies, luarocks.path, packages]
title: LuaRocks & Libraries
description: LuaRocks is the package manager for Lua. Use `luarocks install <package>`. Rockspec defines metadata and dependencies. Manage paths with luarocks.path or package.path/cpath.
source: pattern
---

```lua
-- ==========================
-- LuaRocks Package Management
-- ==========================

-- Install packages (terminal):
--   luarocks install luasocket
--   luarocks install lpeg
--   luarocks install luafilesystem
--   luarocks install penlight

-- Search for packages:
--   luarocks search json

-- List installed:
--   luarocks list

-- Remove:
--   luarocks remove luasocket

-- ==========================
-- Rockspec (my-rock-1.0-1.rockspec)
-- ==========================

-- package = "my-rock"
-- version = "1.0-1"
-- source = {
--   url = "https://example.com/my-rock-1.0.tar.gz"
-- }
-- description = {
--   summary = "A useful Lua library",
--   detailed = "Does something useful",
--   homepage = "https://example.com",
--   license = "MIT"
-- }
-- dependencies = {
--   "lua >= 5.3",
--   "luasocket >= 3.0"
-- }
-- build = {
--   type = "builtin",
--   modules = {
--     ["my_rock"] = "src/my_rock.lua",
--     ["my_rock.util"] = "src/my_rock/util.lua"
--   }
-- }

-- ==========================
-- Using installed packages
-- ==========================

-- LuaRocks adds to package.path and package.cpath automatically
-- when the luarocks launcher is used.

-- Example: using luasocket
-- local socket = require("socket")
-- local http = require("socket.http")
-- local body, code = http.request("http://example.com")

-- Example: using penlight (Lua utility library)
-- local List = require("pl.List")
-- local l = List:new{3, 1, 4, 1, 5}
-- l:sort()
-- print(l:join(", "))  -- "1, 1, 3, 4, 5"

-- ==========================
-- Managing rock paths manually
-- ==========================

-- When using a non-luarocks Lua interpreter:
--   package.path = "/usr/local/share/lua/5.4/?.lua;" .. package.path
--   package.cpath = "/usr/local/lib/lua/5.4/?.so;" .. package.cpath

-- Or use luarocks.path which exports LUA_PATH and LUA_CPATH:
--   $ eval $(luarocks path)
--   $ lua myscript.lua

```
