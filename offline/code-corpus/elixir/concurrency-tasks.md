---
language: elixir
tags: [concurrency, task, async, await, agent, registry, spawn]
title: Concurrency & Tasks
description: Elixir uses lightweight processes. Task.async/await for parallel work, Agent for state, Registry for process discovery, and spawn for raw processes.
source: pattern
---

```elixir
defmodule ConcurrencyDemo do
  @doc "Parallel HTTP fetches with Task.async/await"
  def parallel_fetch(urls) do
    urls
    |> Enum.map(&Task.async(fn -> fetch(&1) end))
    |> Enum.map(&Task.await/1)
  end

  defp fetch(url) do
    {url, :ok}
  end

  @doc "Agent-based counter"
  def agent_counter do
    {:ok, agent} = Agent.start_link(fn -> 0 end)
    Agent.update(agent, &(&1 + 1))
    Agent.update(agent, &(&1 + 1))
    value = Agent.get(agent, & &1)
    Agent.stop(agent)
    value
  end

  @doc "Spawn a simple process that sends itself a message"
  def spawn_demo do
    parent = self()
    spawn(fn ->
      send(parent, {:result, "done"})
    end)
    receive do
      {:result, msg} -> msg
    end
  end

  @doc "Registry — name a process under a key"
  def registry_demo do
    {:ok, _} = Registry.start_link(keys: :unique, name: :my_reg)
    {:ok, _} = Agent.start_link(fn -> %{} end, name: {:via, Registry, {:my_reg, :cache}})
    Registry.lookup(:my_reg, :cache)
  end
end

```
