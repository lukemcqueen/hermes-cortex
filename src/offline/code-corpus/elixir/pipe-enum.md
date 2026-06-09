---
language: elixir
tags: [pipe, enum, stream, comprehension, functional]
title: Pipe Operator & Enum
description: The |> pipe chains function calls left-to-right. Enum.map/filter/reduce are workhorses. Streams are lazy; comprehensions with for offer concise transformations.
source: pattern
---

```elixir
defmodule PipeEnum do
  @doc "Chained pipeline transforming a list"
  def process(numbers) do
    numbers
    |> Enum.filter(&(&1 > 0))
    |> Enum.map(&(&1 * 2))
    |> Enum.reduce(0, &+/2)
  end

  @doc "Lazy stream — elements computed on demand"
  def lazy_squares(limit) do
    1..limit
    |> Stream.map(fn n -> n * n end)
    |> Stream.filter(&(&1 > 10))
    |> Enum.to_list()
  end

  @doc "Comprehension (for) — combine generators and filters"
  def comprehension_sample do
    for x <- [1, 2, 3],
        y <- [:a, :b],
        x > 1,
        do: {x, y}
  end
end

```
