---
language: elixir
tags: [phoenix, controller, liveview, ecto, router, template]
title: Phoenix Framework
description: Phoenix is a web framework built on Elixir/OTP. Key areas: Router (pipeline/scopes), Controller actions, LiveView for real-time UI, Ecto schemas/changesets for persistence.
source: pattern
---

```elixir
# --- Router (lib/my_app_web/router.ex) ---
defmodule MyAppWeb.Router do
  use MyAppWeb, :router

  pipeline :browser do
    plug :accepts, ["html"]
    plug :fetch_session
    plug :fetch_live_flash
    plug :put_root_layout, {MyAppWeb.LayoutView, :root}
  end

  scope "/", MyAppWeb do
    pipe_through :browser
    get  "/",          PageController, :index
    get  "/posts/:id", PostController, :show
    live "/live/:id",  LiveCounter,    :show
  end
end

# --- Controller (lib/my_app_web/controllers/post_controller.ex) ---
defmodule MyAppWeb.PostController do
  use MyAppWeb, :controller

  def show(conn, %{"id" => id}) do
    post = MyApp.Blog.get_post!(id)
    render(conn, "show.html", post: post)
  end
end

# --- LiveView (lib/my_app_web/live/live_counter.ex) ---
defmodule MyAppWeb.LiveCounter do
  use Phoenix.LiveView

  def mount(_params, _session, socket) do
    {:ok, assign(socket, :count, 0)}
  end

  def handle_event("inc", _, socket) do
    {:noreply, update(socket, :count, &(&1 + 1))}
  end
end

# --- Ecto Schema (lib/my_app/blog/post.ex) ---
defmodule MyApp.Blog.Post do
  use Ecto.Schema
  import Ecto.Changeset

  schema "posts" do
    field :title, :string
    field :body, :string
    timestamps()
  end

  def changeset(post, attrs) do
    post
    |> cast(attrs, [:title, :body])
    |> validate_required([:title, :body])
    |> validate_length(:title, min: 3)
  end
end

```
