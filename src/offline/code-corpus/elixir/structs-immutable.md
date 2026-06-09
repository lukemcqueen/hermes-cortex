---
language: elixir
tags: [struct, immutable, map, update_in, get_in, recursion]
title: Immutable Data & Structs
description: Elixir data is immutable. Structs (defstruct) define typed key-value shapes. Use put_in/get_in/update_in for nested access. Recursion replaces loops.
source: pattern
---

```elixir
defmodule Person do
  defstruct [:name, :age, :address]
end

defmodule ImmutableDemo do
  @doc "Struct creation and update"
  def demo_struct do
    alice = %Person{name: "Alice", age: 30, address: %{city: "NYC", zip: "10001"}}
    older_alice = %{alice | age: 31}
    updated = put_in(alice.address[:city], "Brooklyn")
    {alice, older_alice, updated}
  end

  @doc "Recursive map transform (no mutation)"
  def deep_capitalize(map) when is_map(map) do
    Map.new(map, fn {k, v} -> {k, deep_capitalize(v)} end)
  end
  def deep_capitalize(string) when is_binary(string), do: String.upcase(string)
  def deep_capitalize(other), do: other

  @doc "Recursive list sum — classic immutable recursion"
  def sum_list([]), do: 0
  def sum_list([head | tail]), do: head + sum_list(tail)
end

```
