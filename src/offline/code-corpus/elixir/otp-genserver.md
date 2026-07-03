---
language: elixir
tags: [otp, genserver, handle_call, handle_cast, state, start_link]
title: Elixir OTP & GenServer
description: GenServer is the core OTP behaviour for stateful server processes. Define callbacks handle_call/3 (sync), handle_cast/2 (async), handle_info/2 (messages). Use :sys.get_state for debugging.
source: pattern
---

```elixir
defmodule Counter do
  use GenServer

  # Client API

  def start_link(initial_value) do
    GenServer.start_link(__MODULE__, initial_value, name: __MODULE__)
  end

  def increment, do: GenServer.cast(__MODULE__, :increment)
  def decrement, do: GenServer.cast(__MODULE__, :decrement)
  def value,     do: GenServer.call(__MODULE__, :value)

  # Server Callbacks

  @impl true
  def init(initial_value), do: {:ok, initial_value}

  @impl true
  def handle_call(:value, _from, state) do
    {:reply, state, state}
  end

  @impl true
  def handle_cast(:increment, state) do
    {:noreply, state + 1}
  end

  @impl true
  def handle_cast(:decrement, state) do
    {:noreply, state - 1}
  end

  @impl true
  def handle_info({:reset, to}, _state) do
    {:noreply, to}
  end
end

```
