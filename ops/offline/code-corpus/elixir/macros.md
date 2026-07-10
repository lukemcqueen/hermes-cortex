---
language: elixir
tags: [macros, metaprogramming, defmacro, quote, unquote, use, before_compile]
title: Macros & Metaprogramming
description: Macros operate on AST at compile-time. defmacro, quote/unquote, Macro.expand. use/__using__ injects code. @before_compile hooks into final compilation phase.
source: pattern
---

```elixir
defmodule MyMacro do
  @doc "Simple macro: log a message with the calling file and line"
  defmacro log_debug(msg) do
    quote do
      caller = __ENV__
      IO.puts("[#{caller.file}:#{caller.line}] DEBUG: #{unquote(msg)}")
    end
  end

  @doc "Macro that defines a getter function"
  defmacro getter(attr) do
    quote do
      def unquote(:"get_#{attr}")() do
        @unquote(attr)
      end
    end
  end
end

defmodule MyModule do
  @name "Elixir"
  require MyMacro
  MyMacro.getter(:name)

  def test, do: MyMacro.log_debug("macro is working")
end

# ___using___ pattern — inject code when `use` is called
defmodule Injectable do
  defmacro __using__(_opts) do
    quote do
      def hello, do: "world"
    end
  end
end

defmodule Consumer do
  use Injectable
end

```
