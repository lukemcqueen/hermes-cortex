---
language: elixir
tags: [mix, dependencies, config, releases, escript, aliases]
title: Mix & Dependencies
description: Mix is Elixir's build tool. mix.exs defines project metadata, deps, aliases, compilers, and releases. Config for runtime configuration.
source: pattern
---

```elixir
# --- mix.exs ---
defmodule MyApp.MixProject do
  use Mix.Project

  def project do
    [
      app: :my_app,
      version: "0.1.0",
      elixir: "~> 1.15",
      start_permanent: Mix.env() == :prod,
      deps: deps(),
      aliases: aliases(),
      compilers: [:phoenix, :gettext] ++ Mix.compilers(),
      releases: [
        my_app: [
          include_executables_for: [:unix],
          steps: [:assemble, :tar]
        ]
      ]
    ]
  end

  def application do
    [extra_applications: [:logger], mod: {MyApp.Application, []}]
  end

  defp deps do
    [
      {:phoenix, "~> 1.7"},
      {:ecto_sql, "~> 3.10"},
      {:jason, "~> 1.4"},
      {:httpoison, "~> 2.1", only: :dev}
    ]
  end

  defp aliases do
    [
      setup: ["deps.get", "ecto.setup"],
      "ecto.setup": ["ecto.create", "ecto.migrate", "run priv/repo/seeds.exs"],
      test: ["ecto.create --quiet", "ecto.migrate", "test"]
    ]
  end
end

# --- config/config.exs (Elixir 1.15+) ---
import Config

config :my_app, MyApp.Repo,
  database: "my_app_dev",
  username: "postgres",
  password: "postgres",
  hostname: "localhost"

config :my_app, ecto_repos: [MyApp.Repo]

```
