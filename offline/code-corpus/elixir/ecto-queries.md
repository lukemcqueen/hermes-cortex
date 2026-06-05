---
language: elixir
tags: [ecto, query, from, join, preload, changeset, repo]
title: Ecto Queries
description: Ecto.Query with from/2 macro for SQL-like queries. where, join, preload for associations. Repo.all/one/insert/update. Changesets for validation and casting.
source: pattern
---

```elixir
defmodule MyApp.Repo do
  use Ecto.Repo, otp_app: :my_app, adapter: Ecto.Adapters.Postgres
end

defmodule MyApp.Blog.Post do
  use Ecto.Schema

  schema "posts" do
    field :title, :string
    field :body, :string
    field :published, :boolean, default: false
    belongs_to :author, MyApp.Blog.Author
    has_many :comments, MyApp.Blog.Comment
    timestamps()
  end
end

defmodule MyApp.Blog.Author do
  use Ecto.Schema

  schema "authors" do
    field :name, :string
    has_many :posts, MyApp.Blog.Post
    timestamps()
  end
end

defmodule MyApp.Blog.Comment do
  use Ecto.Schema

  schema "comments" do
    field :body, :string
    belongs_to :post, MyApp.Blog.Post
    timestamps()
  end
end

# --- Queries ---
defmodule MyApp.Blog do
  import Ecto.Query
  alias MyApp.Repo
  alias MyApp.Blog.{Post, Author, Comment}

  def published_posts do
    from p in Post,
      where: p.published == true,
      order_by: [desc: p.inserted_at]
    |> Repo.all()
  end

  def posts_by_author(author_name) do
    from p in Post,
      join: a in assoc(p, :author),
      where: a.name == ^author_name,
      preload: [:author, :comments]
    |> Repo.all()
  end

  def create_post(attrs) do
    %Post{}
    |> Post.changeset(attrs)
    |> Repo.insert()
  end

  def update_post(post, attrs) do
    post
    |> Post.changeset(attrs)
    |> Repo.update()
  end

  def get_post_with_comments(id) do
    from p in Post,
      where: p.id == ^id,
      preload: [comments: :post]
    |> Repo.one()
  end
end

# --- Changeset ---
defmodule MyApp.Blog.Post do
  use Ecto.Schema
  import Ecto.Changeset

  def changeset(post, attrs) do
    post
    |> cast(attrs, [:title, :body, :published, :author_id])
    |> validate_required([:title, :body])
    |> validate_length(:title, min: 3, max: 200)
    |> validate_length(:body, max: 10_000)
    |> assoc_constraint(:author)
  end
end

```
