---
language: elixir
tags: [error-handling, try, rescue, with, tuple, ok-error]
title: Error Handling & Try
description: Elixir discourages exceptions in favor of {:ok, result} / {:error, reason} tuples. Use try/rescue/after for exceptional cases, with/else for error chains.
source: pattern
---

```elixir
defmodule ErrorHandling do
  @doc "Tuple-based error handling — idiomatic Elixir"
  def divide(a, b) when b == 0, do: {:error, "division by zero"}
  def divide(a, b), do: {:ok, a / b}

  @doc "with/else — chain operations that return tagged tuples"
  def with_chain(a, b, c) do
    with {:ok, x} <- divide(a, b),
         {:ok, y} <- divide(x, c) do
      {:ok, y}
    else
      {:error, reason} -> {:error, "chain failed: #{reason}"}
    end
  end

  @doc "try/rescue/after — for exceptional code (e.g., external libs)"
  def try_rescue_demo(path) do
    try do
      File.read!(path)
    rescue
      File.Error -> {:error, "file problem"}
      e in ArgumentError -> {:error, "argument: #{e.message}"}
    after
      IO.puts("executed regardless of success/failure")
    end
  end

  @doc "Catch exit signals from linked processes"
  def catch_exit do
    spawn_link(fn -> Process.exit(self(), :killed) end)
    receive do
      {:EXIT, _, reason} -> {:exit_caught, reason}
    end
  end
end

```
