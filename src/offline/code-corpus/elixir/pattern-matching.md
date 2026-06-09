---
language: elixir
tags: [pattern-matching, guards, pin, case, cond, with]
title: Pattern Matching & Guard Clauses
description: Pattern matching is the heart of Elixir. Use = for match, ^ to pin a variable, case/cond/with for control flow, and when guards for extra constraints.
source: pattern
---

```elixir
# Pattern matching, guards, pin operator, case, cond, with
defmodule Patterns do
  # Function head matching with guards
  def describe(number) when is_integer(number) and number > 0, do: "positive integer"
  def describe(number) when is_integer(number) and number < 0, do: "negative integer"
  def describe(0), do: "zero"
  def describe(other) when is_float(other), do: "float: #{other}"
  def describe(_), do: "unknown"

  # Pin operator (^) — match against existing value, not rebind
  def pin_example do
    expected = 42
    case 42 do
      ^expected -> "matched pinned 42"
      _ -> "no match"
    end
  end

  # cond — first truthy clause wins
  def classify(x) do
    cond do
      x < 0  -> "negative"
      x == 0 -> "zero"
      x > 0  -> "positive"
      true   -> "not a number"
    end
  end

  # with — chain pattern-matching steps; else handles failures
  def with_example(map) do
    with {:ok, name} <- Map.fetch(map, :name),
         {:ok, age}  <- Map.fetch(map, :age) do
      "#{name} is #{age} years old"
    else
      :error -> "missing key"
    end
  end
end

```
