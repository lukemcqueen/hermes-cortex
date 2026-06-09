"""Elixir (10) + Lua (10) + R (12) snippet module.
Each entry is a 7-tuple:
  (rel_path, language, tags, title, description, source, code)
"""

SNIPPETS = [
    # =========================================================================
    # ELIXIR (10)
    # =========================================================================
    (
        "elixir/pattern-matching.md",
        "elixir",
        ["pattern-matching", "guards", "pin", "case", "cond", "with"],
        "Pattern Matching & Guard Clauses",
        "Pattern matching is the heart of Elixir. Use = for match, ^ to pin a variable, case/cond/with for control flow, and when guards for extra constraints.",
        "pattern",
        """# Pattern matching, guards, pin operator, case, cond, with
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
""",
    ),
    (
        "elixir/otp-genserver.md",
        "elixir",
        ["otp", "genserver", "handle_call", "handle_cast", "state", "start_link"],
        "Elixir OTP & GenServer",
        "GenServer is the core OTP behaviour for stateful server processes. Define callbacks handle_call/3 (sync), handle_cast/2 (async), handle_info/2 (messages). Use :sys.get_state for debugging.",
        "pattern",
        """defmodule Counter do
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
""",
    ),
    (
        "elixir/pipe-enum.md",
        "elixir",
        ["pipe", "enum", "stream", "comprehension", "functional"],
        "Pipe Operator & Enum",
        "The |> pipe chains function calls left-to-right. Enum.map/filter/reduce are workhorses. Streams are lazy; comprehensions with for offer concise transformations.",
        "pattern",
        """defmodule PipeEnum do
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
""",
    ),
    (
        "elixir/phoenix.md",
        "elixir",
        ["phoenix", "controller", "liveview", "ecto", "router", "template"],
        "Phoenix Framework",
        "Phoenix is a web framework built on Elixir/OTP. Key areas: Router (pipeline/scopes), Controller actions, LiveView for real-time UI, Ecto schemas/changesets for persistence.",
        "pattern",
        """# --- Router (lib/my_app_web/router.ex) ---
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
""",
    ),
    (
        "elixir/structs-immutable.md",
        "elixir",
        ["struct", "immutable", "map", "update_in", "get_in", "recursion"],
        "Immutable Data & Structs",
        "Elixir data is immutable. Structs (defstruct) define typed key-value shapes. Use put_in/get_in/update_in for nested access. Recursion replaces loops.",
        "pattern",
        """defmodule Person do
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
""",
    ),
    (
        "elixir/concurrency-tasks.md",
        "elixir",
        ["concurrency", "task", "async", "await", "agent", "registry", "spawn"],
        "Concurrency & Tasks",
        "Elixir uses lightweight processes. Task.async/await for parallel work, Agent for state, Registry for process discovery, and spawn for raw processes.",
        "pattern",
        """defmodule ConcurrencyDemo do
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
""",
    ),
    (
        "elixir/error-handling.md",
        "elixir",
        ["error-handling", "try", "rescue", "with", "tuple", "ok-error"],
        "Error Handling & Try",
        "Elixir discourages exceptions in favor of {:ok, result} / {:error, reason} tuples. Use try/rescue/after for exceptional cases, with/else for error chains.",
        "pattern",
        """defmodule ErrorHandling do
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
""",
    ),
    (
        "elixir/macros.md",
        "elixir",
        ["macros", "metaprogramming", "defmacro", "quote", "unquote", "use", "before_compile"],
        "Macros & Metaprogramming",
        "Macros operate on AST at compile-time. defmacro, quote/unquote, Macro.expand. use/__using__ injects code. @before_compile hooks into final compilation phase.",
        "pattern",
        """defmodule MyMacro do
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
""",
    ),
    (
        "elixir/mix-deps.md",
        "elixir",
        ["mix", "dependencies", "config", "releases", "escript", "aliases"],
        "Mix & Dependencies",
        "Mix is Elixir's build tool. mix.exs defines project metadata, deps, aliases, compilers, and releases. Config for runtime configuration.",
        "pattern",
        """# --- mix.exs ---
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
""",
    ),
    (
        "elixir/ecto-queries.md",
        "elixir",
        ["ecto", "query", "from", "join", "preload", "changeset", "repo"],
        "Ecto Queries",
        "Ecto.Query with from/2 macro for SQL-like queries. where, join, preload for associations. Repo.all/one/insert/update. Changesets for validation and casting.",
        "pattern",
        """defmodule MyApp.Repo do
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
""",
    ),

    # =========================================================================
    # LUA (10)
    # =========================================================================
    (
        "lua/tables.md",
        "lua",
        ["tables", "arrays", "dictionaries", "insert", "remove", "sort", "pairs", "ipairs"],
        "Tables as Arrays/Dicts",
        "Lua tables serve as both arrays and dictionaries. Use table.insert/remove/sort, # for length, pairs/ipairs for iteration. Table is the only data-structure.",
        "pattern",
        """-- Tables double as arrays (1-indexed) and dictionaries
local t = {10, 20, 30}          -- array part
t["key"] = "value"              -- dict part
t.speed = 100                   -- syntactic sugar for t["speed"]

-- Insert / Remove
table.insert(t, 40)             -- append
table.insert(t, 2, 15)          -- insert 15 at index 2
table.remove(t, 3)              -- remove element at index 3

-- Length (#) works on array-portion (contiguous integer keys)
print(#t)                       -- count of array-part

-- Iteration
for i, v in ipairs(t) do        -- ipairs: 1-indexed integer keys only
  print(i, v)
end

for k, v in pairs(t) do         -- pairs: all keys
  print(k, v)
end

-- Sort
local names = {"Charlie", "Alice", "Bob"}
table.sort(names)               -- alphabetical
table.sort(names, function(a, b) return #a < #b end)

-- Mixed usage
local inventory = {
  apples = 10,
  oranges = 5,
  {name = "sword", damage = 50},
  {name = "shield", defense = 30},
}
print(inventory.apples)          -- 10
print(inventory[1].name)         -- "sword"
""",
    ),
    (
        "lua/metatables.md",
        "lua",
        ["metatables", "oop", "setmetatable", "__index", "__call", "__add", "__tostring"],
        "Metatables & OOP",
        "Metatables control table behaviour via events (__index, __call, __add, __tostring, etc.). Use __index for prototype-based OOP — the classic Lua class pattern.",
        "pattern",
        """-- Metatable events
local t = {}
local mt = {
  __index = {greeting = "Hello"},         -- fallback lookup
  __newindex = function(t, k, v)          -- intercept writes
    print("Setting " .. k .. " = " .. tostring(v))
    rawset(t, k, v)
  end,
  __call = function(t, ...)               -- make table callable
    return "Called with " .. select("#", ...) .. " args"
  end,
  __tostring = function(t)
    local parts = {}
    for k, v in pairs(t) do
      table.insert(parts, k .. "=" .. tostring(v))
    end
    return "{" .. table.concat(parts, ", ") .. "}"
  end,
  __add = function(a, b)
    return setmetatable({x = a.x + b.x, y = a.y + b.y}, getmetatable(a))
  end,
}
setmetatable(t, mt)

-- Prototype-based OOP (class pattern)
local Animal = {}
Animal.__index = Animal

function Animal:new(name, sound)
  return setmetatable({name = name, sound = sound}, self)
end

function Animal:speak()
  print(self.name .. " says " .. self.sound)
end

local Dog = setmetatable({}, {__index = Animal})
Dog.__index = Dog

function Dog:new(name)
  return setmetatable({name = name, sound = "Woof!"}, self)
end

function Dog:fetch()
  print(self.name .. " fetches the stick")
end

local fido = Dog:new("Fido")
fido:speak()
fido:fetch()
""",
    ),
    (
        "lua/functions-closures.md",
        "lua",
        ["functions", "closures", "upvalues", "variadic", "tail-calls", "coroutines"],
        "Functions & Closures",
        "Lua has first-class functions with lexical scoping. Closures capture upvalues. Variadic ... arguments. Tail calls reuse stack frame. Coroutines for cooperative multitasking.",
        "pattern",
        """-- First-class function assigned to variable
local greet = function(name)
  return "Hello, " .. name
end
print(greet("Lua"))  -- "Hello, Lua"

-- Closure capturing an upvalue
function make_counter(start)
  local count = start
  return function()
    count = count + 1
    return count
  end
end

local counter = make_counter(10)
print(counter())  -- 11
print(counter())  -- 12

-- Variadic function (arbitrary arguments)
function sum(...)
  local total = 0
  for _, v in ipairs({...}) do
    total = total + v
  end
  return total
end
print(sum(1, 2, 3, 4, 5))  -- 15

-- Named + variadic with select
function printf(fmt, ...)
  local args = {...}
  for i = 1, select("#", ...) do end
  print(string.format(fmt, ...))
end

-- Tail call (no extra stack frame)
function factorial(n, acc)
  acc = acc or 1
  if n <= 1 then return acc end
  return factorial(n - 1, n * acc)  -- tail call
end
print(factorial(5))  -- 120

-- Coroutine as closure-based generator
function range_gen(limit)
  return coroutine.wrap(function()
    for i = 1, limit do
      coroutine.yield(i)
    end
  end)
end

local gen = range_gen(3)
print(gen())  -- 1
print(gen())  -- 2
print(gen())  -- 3
print(gen())  -- nil (done)
""",
    ),
    (
        "lua/file-io.md",
        "lua",
        ["file-io", "io.open", "read", "write", "io.lines", "string.find", "gmatch"],
        "File I/O",
        "Lua's io library provides File I/O: io.open returns a file handle. Read modes: \"*a\" (all), \"*l\" (line), \"*n\" (number). io.lines for line-by-line iteration. Useful with string.find/gmatch.",
        "pattern",
        """-- Write to file
local f = io.open("example.txt", "w")
if f then
  f:write("Line 1\\n")
  f:write("Line 2\\n")
  f:close()
end

-- Read entire file
local f = io.open("example.txt", "r")
if f then
  local content = f:read("*a")
  f:close()
  print(content)
end

-- Read line by line
local f = io.open("example.txt", "r")
if f then
  for line in f:lines() do
    print(">> " .. line)
  end
  f:close()
end

-- io.lines — open and iterate in one step
for line in io.lines("example.txt") do
  if string.find(line, "Line") then
    print("Found: " .. line)
  end
end

-- Pattern matching with data from file
local log = [[
2024-01-01 INFO  started
2024-01-01 ERROR disk full
2024-01-02 INFO  completed
]]

for line in string.gmatch(log, "[^\\n]+") do
  local date, level, msg = string.match(line, "(%S+) (%S+) (.+)")
  if level == "ERROR" then
    print("ERROR on " .. date .. ": " .. msg)
  end
end

-- Append to file
local f = io.open("example.txt", "a")
if f then
  f:write("Appended line\\n")
  f:close()
end
""",
    ),
    (
        "lua/patterns-strings.md",
        "lua",
        ["strings", "patterns", "match", "gmatch", "gsub", "captures", "string-library"],
        "Lua Patterns & Strings",
        "Lua has a lightweight pattern language (not full regex). string.match/gmatch/gsub/sub/upper/lower/rep/format. Captures with (). Character classes: %d, %a, %s, etc.",
        "pattern",
        """-- String basics
local s = "  Hello, Lua!  "
print(string.len(s))          -- 15
print(string.upper(s))        -- "  HELLO, LUA!  "
print(string.lower(s))        -- "  hello, lua!  "
print(string.sub(s, 3, 7))    -- "Hello"
print(string.rep("Ha", 3))    -- "HaHaHa"
print(string.format("\\u03c0 \\u2248 %.3f", math.pi))  -- "\\u03c0 \\u2248 3.142"

-- Patterns (not regex)
local text = "hello 123 world 456"

-- string.find returns start, end indices
local s, e = string.find(text, "%d+")
print(s, e)  -- 7, 9 ("123")

-- string.match returns first capture or full match
local num = string.match(text, "(%d+)")
print(num)  -- "123"

-- string.gmatch iterates all matches
for n in string.gmatch(text, "(%d+)") do
  print(n)
end

-- string.gsub replaces globally
local result, count = string.gsub("one, two, one", "one", "1")
print(result)  -- "1, two, 1"
print(count)   -- 2

-- Captures in patterns
local email = "user@example.com"
local name, domain = string.match(email, "([^@]+)@(.+)")
print(name, domain)  -- "user"  "example.com"

-- Character classes: %d (digit), %a (letter), %s (space), %w (alnum), %p (punct)
local csv = "a,b,c,d"
for field in string.gmatch(csv, "([^,]+)") do
  print(field)
end
""",
    ),
    (
        "lua/coroutines.md",
        "lua",
        ["coroutines", "coroutine.wrap", "resume", "yield", "producer-consumer", "coroutine.status"],
        "Coroutines",
        "Coroutines provide cooperative multitasking. coroutine.create/resume/yield. coroutine.wrap returns a callable wrapper. Use for generators, producer-consumer, state machines.",
        "pattern",
        """-- Basic coroutine
local co = coroutine.create(function()
  print("coroutine started")
  local val = coroutine.yield("first yield")
  print("received: " .. val)
  return "done"
end)

local status, result = coroutine.resume(co)
print("main got: " .. result)

status, result = coroutine.resume(co, "hello from main")
print("main got: " .. result)

print("status: " .. coroutine.status(co))  -- "dead"

-- coroutine.wrap (simpler, no status returned)
local wrap = coroutine.wrap(function()
  for i = 1, 5 do
    coroutine.yield(i * 2)
  end
end)

for _ = 1, 5 do
  print(wrap())  -- 2, 4, 6, 8, 10
end

-- Producer-Consumer pattern
function producer(consumer)
  return coroutine.wrap(function()
    for i = 1, 5 do
      print("producing " .. i)
      consumer(i)
    end
  end)
end

function consumer()
  return coroutine.create(function()
    while true do
      local _, value = coroutine.yield()
      print("consuming " .. value)
    end
  end)
end

-- Filter coroutine (pipeline)
function filter(source, predicate)
  return coroutine.wrap(function()
    for value in source do
      if predicate(value) then
        coroutine.yield(value)
      end
    end
  end)
end

local numbers = coroutine.wrap(function()
  for i = 1, 10 do coroutine.yield(i) end
end)

local evens = filter(numbers, function(n) return n % 2 == 0 end)
for n in evens do
  print(n)  -- 2, 4, 6, 8, 10
end
""",
    ),
    (
        "lua/modules-require.md",
        "lua",
        ["modules", "require", "package.path", "return-table", "local-functions", "module-pattern"],
        "Modules & require",
        "Lua modules are files returning a table. require caches loaded modules. package.path controls search locations. Local functions hide internal details; only exported ones go in the return table.",
        "pattern",
        """-- mylib.lua
-- Local (private) functions
local function private_helper(x)
  return x * 2
end

-- Public functions returned in the module table
local mylib = {}

function mylib.greet(name)
  return "Hello, " .. name
end

function mylib.double(n)
  return private_helper(n)
end

function mylib.process_list(t)
  local result = {}
  for _, v in ipairs(t) do
    table.insert(result, private_helper(v))
  end
  return result
end

mylib.version = "1.0.0"

return mylib
""",
    ),
    (
        "lua/error-pcall.md",
        "lua",
        ["error-handling", "pcall", "xpcall", "error", "assert", "debug.traceback", "protected-calls"],
        "Error Handling & pcall",
        "pcall (protected call) catches runtime errors without crashing. xpcall adds an error handler. error() raises an error, assert() as validation. debug.traceback provides stack traces.",
        "pattern",
        """-- pcall — protected call, returns status + results
local function risky(n)
  if n == 0 then
    error("cannot divide by zero!")
  end
  return 100 / n
end

local ok, result = pcall(risky, 5)
if ok then
  print("success:", result)    -- 20
else
  print("error:", result)
end

local ok, err = pcall(risky, 0)
print(ok, err)  -- false, "cannot divide by zero!"

-- xpcall — protected call with error handler
local function error_handler(err)
  print("caught:", err)
  print(debug.traceback())
  return "handled: " .. err
end

local ok, result = xpcall(risky, error_handler, 0)
print(ok, result)

-- assert — raises error if condition is false
local file = assert(io.open("nonexistent.txt", "r"), "file not found")

-- Custom assert style
local function ensure(cond, msg)
  if not cond then
    error(msg or "assertion failed", 2)
  end
end

-- Multiple return values from pcall
local function read_safe(path)
  local f, err = io.open(path, "r")
  if not f then return nil, err end
  local content = f:read("*a")
  f:close()
  return content
end

local ok, content_or_err = pcall(read_safe, "config.lua")
if ok then
  print(content_or_err)
else
  io.stderr:write("error: " .. content_or_err .. "\\n")
end
""",
    ),
    (
        "lua/c-api-ffi.md",
        "lua",
        ["c-api", "ffi", "luajit", "lua_State", "ffi.cdef", "ffi.new", "ffi.C"],
        "C API & FFI",
        "Lua's C API uses lua_State and stack-based operations. LuaJIT's FFI (ffi.cdef/ffi.new/ffi.C) allows direct C function calls and struct access from Lua, much faster than the C API.",
        "pattern",
        """-- =====================
-- LuaJIT FFI (preferred)
-- =====================
local ffi = require("ffi")

-- Declare C types and functions
ffi.cdef[[
  typedef struct { double x, y; } point_t;
  double sqrt(double x);
  int printf(const char *fmt, ...);
  int fact(int n);
]]

-- Load a shared library (if needed)
local mylib = ffi.load("mylib")

-- Use C structs
local p = ffi.new("point_t", {x = 3.0, y = 4.0})
print(p.x, p.y)  -- 3.0  4.0

-- Call C functions
local dist = ffi.C.sqrt(p.x * p.x + p.y * p.y)
print(dist)  -- 5.0

ffi.C.printf("distance = %f\\n", dist)

-- Arrays
local arr = ffi.new("int[?]", 10, {1, 2, 3})
for i = 0, 9 do
  arr[i] = arr[i] + 1
end
""",
    ),
    (
        "lua/luarocks-libs.md",
        "lua",
        ["luarocks", "install", "rockspec", "dependencies", "luarocks.path", "packages"],
        "LuaRocks & Libraries",
        "LuaRocks is the package manager for Lua. Use `luarocks install <package>`. Rockspec defines metadata and dependencies. Manage paths with luarocks.path or package.path/cpath.",
        "pattern",
        """-- ==========================
-- LuaRocks Package Management
-- ==========================

-- Install packages (terminal):
--   luarocks install luasocket
--   luarocks install lpeg
--   luarocks install luafilesystem
--   luarocks install penlight

-- Search for packages:
--   luarocks search json

-- List installed:
--   luarocks list

-- Remove:
--   luarocks remove luasocket

-- ==========================
-- Rockspec (my-rock-1.0-1.rockspec)
-- ==========================

-- package = "my-rock"
-- version = "1.0-1"
-- source = {
--   url = "https://example.com/my-rock-1.0.tar.gz"
-- }
-- description = {
--   summary = "A useful Lua library",
--   detailed = "Does something useful",
--   homepage = "https://example.com",
--   license = "MIT"
-- }
-- dependencies = {
--   "lua >= 5.3",
--   "luasocket >= 3.0"
-- }
-- build = {
--   type = "builtin",
--   modules = {
--     ["my_rock"] = "src/my_rock.lua",
--     ["my_rock.util"] = "src/my_rock/util.lua"
--   }
-- }

-- ==========================
-- Using installed packages
-- ==========================

-- LuaRocks adds to package.path and package.cpath automatically
-- when the luarocks launcher is used.

-- Example: using luasocket
-- local socket = require("socket")
-- local http = require("socket.http")
-- local body, code = http.request("http://example.com")

-- Example: using penlight (Lua utility library)
-- local List = require("pl.List")
-- local l = List:new{3, 1, 4, 1, 5}
-- l:sort()
-- print(l:join(", "))  -- "1, 1, 3, 4, 5"

-- ==========================
-- Managing rock paths manually
-- ==========================

-- When using a non-luarocks Lua interpreter:
--   package.path = "/usr/local/share/lua/5.4/?.lua;" .. package.path
--   package.cpath = "/usr/local/lib/lua/5.4/?.so;" .. package.cpath

-- Or use luarocks.path which exports LUA_PATH and LUA_CPATH:
--   $ eval $(luarocks path)
--   $ lua myscript.lua
""",
    ),

    # =========================================================================
    # R (12)
    # =========================================================================
    (
        "r/vectors-data-types.md",
        "r",
        ["vectors", "c", "seq", "rep", "factors", "NA", "is.na", "na.omit"],
        "Vectors & Data Types",
        "Vectors are the atomic data type in R. Use c(), seq(), rep() to create them. Factors for categorical data. NA handling: is.na(), na.omit(), na.rm=TRUE.",
        "pattern",
        """# Vector creation
v1 <- c(1, 2, 3, 4, 5)           # numeric vector
v2 <- c("a", "b", "c")            # character vector
v3 <- c(TRUE, FALSE, TRUE)        # logical vector

# Sequence and repetition
seq(1, 10, by = 2)                # 1 3 5 7 9
1:5                                # 1 2 3 4 5
rep(1:3, times = 2)               # 1 2 3 1 2 3
rep(1:3, each = 2)                # 1 1 2 2 3 3

# Vector types
typeof(v1)                         # "double"
is.numeric(v1)                     # TRUE
is.character(v2)                   # TRUE

# Coercion (all elements become same type)
mixed <- c(1, "two", TRUE)         # all become character: "1", "two", "TRUE"

# Factors — categorical data
gender <- factor(c("M", "F", "F", "M", "F"))
levels(gender)                     # "F" "M"
table(gender)                      # F M  (counts)

# Ordered factor
rating <- ordered(c("low", "high", "medium"),
                   levels = c("low", "medium", "high"))

# NA handling
x <- c(1, 2, NA, 4, NA, 6)
is.na(x)                           # FALSE FALSE TRUE FALSE TRUE FALSE
sum(is.na(x))                      # 2
na.omit(x)                         # removes NA entries (with attributes)
mean(x, na.rm = TRUE)              # (1+2+4+6)/4 = 3.25

# Vectorized operations
v1 <- 1:5
v2 <- 6:10
v1 + v2                            # 7  9 11 13 15
v1^2                               # 1  4  9 16 25
v1 > 3                             # FALSE FALSE FALSE TRUE TRUE
""",
    ),
    (
        "r/data-frames.md",
        "r",
        ["data-frame", "tibble", "dplyr", "filter", "select", "mutate", "arrange", "summarise", "pipe"],
        "Data Frames & Tibbles",
        "data.frame and tibble (tidyverse) are the workhorses for tabular data. dplyr verbs: filter/select/mutate/arrange/summarise. The %>% pipe chains operations. Tibbles print nicely and don't auto-convert strings.",
        "pattern",
        """# Base R data.frame
df <- data.frame(
  name = c("Alice", "Bob", "Charlie"),
  age  = c(25, 30, 35),
  city = c("NYC", "LA", "Chicago"),
  stringsAsFactors = FALSE
)

# Access columns
df$name                            # vector
df[, "age"]                        # column
df[2, ]                            # row 2
df[1:2, c("name", "city")]        # subset rows and columns

# Tibble (tidyverse)
library(tibble)
tbl <- tibble(
  name = c("Alice", "Bob", "Charlie"),
  age  = c(25, 30, 35),
  city = c("NYC", "LA", "Chicago")
)

# dplyr chained with pipe
library(dplyr)

tbl %>%
  filter(age > 28) %>%
  select(name, age) %>%
  mutate(age_group = ifelse(age > 30, "30+", "20-30")) %>%
  arrange(desc(age)) %>%
  summarise(avg_age = mean(age, na.rm = TRUE))

# Adding columns
tbl <- tbl %>%
  mutate(
    age_sq = age^2,
    is_adult = age >= 18
  )

# Rename
tbl %>% rename(full_name = name)

# Distinct rows
tbl %>% distinct(city)
""",
    ),
    (
        "r/tidyverse-dplyr-tidyr.md",
        "r",
        ["tidyverse", "dplyr", "tidyr", "group_by", "summarise", "across", "pivot", "join"],
        "Tidyverse: dplyr & tidyr",
        "dplyr's group_by + summarise/across for grouped operations. tidyr's pivot_longer/wider reshape data. separate/unite split/merge columns. Join functions: left_join, inner_join, etc.",
        "pattern",
        """library(dplyr)
library(tidyr)

# =====================
# Grouped operations
# =====================
df <- tibble(
  group  = rep(c("A", "B"), each = 4),
  gender = rep(c("M", "F"), times = 4),
  value  = c(1, 2, 3, 4, 5, 6, 7, 8)
)

df %>%
  group_by(group, gender) %>%
  summarise(
    avg = mean(value),
    sum = sum(value),
    n   = n(),
    .groups = "drop"
  )

# across — apply function to multiple columns
df %>%
  group_by(group) %>%
  summarise(
    across(where(is.numeric), list(mean = mean, sd = sd)),
    .groups = "drop"
  )

# =====================
# pivot_longer / pivot_wider
# =====================
wide <- tibble(
  id = 1:3,
  a  = c(10, 20, 30),
  b  = c(40, 50, 60)
)

# Wide -> Long
long <- wide %>%
  pivot_longer(cols = c(a, b),
               names_to = "variable",
               values_to = "value")

# Long -> Wide
wide_again <- long %>%
  pivot_wider(names_from = variable,
              values_from = value)

# =====================
# separate / unite
# =====================
df <- tibble(full_name = c("John Smith", "Jane Doe"))
df <- df %>%
  separate(full_name, into = c("first", "last"), sep = " ")
df %>% unite("full_name", first, last, sep = " ")

# =====================
# Joins
# =====================
x <- tibble(id = 1:3, name = c("A", "B", "C"))
y <- tibble(id = c(2, 3, 4), score = c(90, 85, 95))

inner_join(x, y, by = "id")      # rows 2,3 only
left_join(x, y, by = "id")       # all from x, NA for id=1
right_join(x, y, by = "id")      # all from y, NA for id=4
full_join(x, y, by = "id")       # all rows from both
semi_join(x, y, by = "id")       # rows in x that have match in y
anti_join(x, y, by = "id")       # rows in x WITHOUT match in y
""",
    ),
    (
        "r/ggplot2.md",
        "r",
        ["ggplot2", "ggplot", "aes", "geom_point", "geom_line", "geom_bar", "geom_histogram", "facet_wrap", "theme"],
        "ggplot2",
        "ggplot2 implements the Grammar of Graphics. Start with ggplot() + aes() + geom_*(). Add themes, facets, labels. ggsave() saves to file. Scales control colours, axes, legends.",
        "pattern",
        """library(ggplot2)

# Basic scatter plot
ggplot(mtcars, aes(x = wt, y = mpg)) +
  geom_point(color = "steelblue", size = 3, alpha = 0.7) +
  labs(title = "MPG vs Weight",
       x = "Weight (1000 lbs)",
       y = "Miles per Gallon") +
  theme_minimal()

# Bar chart
ggplot(diamonds, aes(x = cut)) +
  geom_bar(fill = "tomato") +
  labs(title = "Diamond Cut Distribution") +
  theme_classic()

# Histogram with density overlay
ggplot(faithful, aes(x = eruptions)) +
  geom_histogram(aes(y = after_stat(density)),
                 bins = 30,
                 fill = "skyblue",
                 color = "white") +
  geom_density(color = "darkred", linewidth = 1) +
  labs(title = "Old Faithful Eruption Times")

# Line plot (time series)
df <- data.frame(
  year = 2010:2020,
  value = c(10, 12, 15, 14, 18, 20, 22, 25, 24, 28, 30)
)
ggplot(df, aes(x = year, y = value)) +
  geom_line(color = "green4", linewidth = 1.2) +
  geom_point(color = "darkgreen", size = 3) +
  theme_bw()

# Facets
ggplot(mtcars, aes(x = wt, y = mpg)) +
  geom_point() +
  facet_wrap(~ cyl, scales = "free") +
  theme_light()

# Custom theme
ggplot(mtcars, aes(x = factor(cyl), y = mpg, fill = factor(cyl))) +
  geom_boxplot() +
  scale_fill_brewer(palette = "Set2") +
  theme(
    legend.position = "bottom",
    panel.grid.major.x = element_blank(),
    text = element_text(size = 14)
  ) +
  labs(title = "MPG by Cylinder Count")
""",
    ),
    (
        "r/base-plotting.md",
        "r",
        ["base-r", "plot", "hist", "boxplot", "par", "lines", "points", "legend", "custom-axes"],
        "Base R Plotting",
        "Base R plotting with plot(), hist(), boxplot(). par() for graphical parameters. lines()/points() overlay. legend() for keys. Custom axes with axis(). Powerful but imperative.",
        "pattern",
        """# Basic scatter plot
x <- 1:10
y <- rnorm(10, mean = 5, sd = 2)
plot(x, y, main = "Scatter Plot", xlab = "Index", ylab = "Value",
     pch = 19, col = "blue", cex = 1.5)

# Overlay a line
abline(lm(y ~ x), col = "red", lwd = 2)

# Histogram
hist(mtcars$mpg,
     breaks = 10,
     col = "steelblue",
     border = "white",
     main = "Distribution of MPG",
     xlab = "Miles per Gallon")

# Add density curve
hist(mtcars$mpg, breaks = 10, col = "lightgray",
     border = "white", freq = FALSE, main = "MPG with Density")
lines(density(mtcars$mpg), col = "darkred", lwd = 2)

# Boxplot
boxplot(mpg ~ cyl, data = mtcars,
        col = c("red", "green", "blue"),
        main = "MPG by Cylinder",
        xlab = "Cylinders", ylab = "MPG")

# Multiple plots in one device (layout)
par(mfrow = c(2, 2))       # 2x2 grid
plot(mtcars$wt, mtcars$mpg, main = "wt vs mpg")
hist(mtcars$mpg, main = "Histogram")
boxplot(mtcars$hp, main = "HP Boxplot")
plot(mtcars$disp, mtcars$hp, main = "disp vs hp")
par(mfrow = c(1, 1))       # reset

# Custom axes
plot(x, y, xaxt = "n", yaxt = "n", type = "n")
axis(1, at = 1:10, labels = letters[1:10], las = 2)
axis(2, at = seq(0, 10, by = 2), las = 1)
points(x, y, pch = 19, col = "darkgreen")
legend("topleft", legend = "Data points", pch = 19, col = "darkgreen")
""",
    ),
    (
        "r/statistical-tests.md",
        "r",
        ["lm", "glm", "t.test", "chisq.test", "summary", "predict", "broom"],
        "Statistical Tests & Models",
        "R excels at statistics: lm() for linear models, glm() for generalized linear models, t.test(), chisq.test(). summary() for model output. predict() for predictions. broom::tidy for clean output.",
        "pattern",
        """# =====================
# Linear Model (lm)
# =====================
model <- lm(mpg ~ wt + hp, data = mtcars)
summary(model)                       # coefficients, R-squared, p-values
coef(model)                          # coefficients only
confint(model)                       # confidence intervals

# Predictions
new_data <- data.frame(wt = c(2.5, 3.0), hp = c(100, 150))
predict(model, newdata = new_data)
predict(model, newdata = new_data, interval = "confidence")

# Diagnostics
plot(model)

# =====================
# Generalized Linear Model (glm)
# =====================
glm_model <- glm(am ~ wt + hp, data = mtcars, family = binomial)
summary(glm_model)
predict(glm_model, type = "response")  # probabilities

# =====================
# t-test
# =====================
t.test(mpg ~ am, data = mtcars)                   # two-sample
t.test(mtcars$mpg, mu = 20)                        # one-sample
t.test(mtcars$mpg, mtcars$hp, paired = FALSE)

# =====================
# Chi-squared test
# =====================
tbl <- table(mtcars$cyl, mtcars$am)
chisq.test(tbl)

# =====================
# broom::tidy — clean output
# =====================
library(broom)
tidy(model)                          # coefficient table as tibble
glance(model)                        # model-level stats (R-squared, AIC, etc.)
augment(model)                       # original data + fitted/residuals

# Example workflow
library(broom)
models <- mtcars %>%
  group_by(cyl) %>%
  summarise(model = list(lm(mpg ~ wt, data = pick(everything())))) %>%
  mutate(tidied = map(model, tidy))
""",
    ),
    (
        "r/string-manipulation.md",
        "r",
        ["stringr", "str_detect", "str_replace", "str_extract", "str_split", "str_trim", "regex"],
        "String Manipulation",
        "stringr (tidyverse) provides consistent string functions: str_detect/filter, str_replace/extract, str_split, str_trim, str_pad, str_to_upper/lower. Base R also has grep/gsub/regexpr.",
        "pattern",
        """library(stringr)

# =====================
# stringr (tidyverse)
# =====================
text <- c("Hello World", "hello R", "Hi there!", "HELLO AGAIN")

# Detect
str_detect(text, "hello")          # FALSE  TRUE FALSE FALSE
str_which(text, "Hello")           # 1 (index)
str_subset(text, "!")              # "Hi there!"

# Replace
str_replace(text, "hello", "bye")           # first match only
str_replace_all(text, "HELLO", "GOODBYE")   # all matches
str_remove(text, "!")                       # remove first match

# Extract
str_extract(text, "[A-Z]+")               # "H" "H" "H" "HELLO"
str_extract_all(text, "[A-Za-z]+")        # list of all words
str_match(text, "(\\\\w+) (\\\\w+)")          # captures as matrix

# Split
str_split("a,b,c", ",")                    # list("a", "b", "c")
str_split_fixed("a,b,c", ",", n = 2)      # matrix: "a" "b,c"

# Trim / Pad
str_trim("  padded  ")                    # "padded"
str_pad("7", width = 3, pad = "0")       # "007"

# Case conversion
str_to_upper("hello")                     # "HELLO"
str_to_lower("HELLO")                     # "hello"
str_to_title("hello world")              # "Hello World"

# Length and subset
str_length("hello")                       # 5
str_sub("hello", 2, 4)                    # "ell"

# Regex groups
dates <- c("2024-01-15", "2023-12-25")
str_match(dates, "(\\\\d{4})-(\\\\d{2})-(\\\\d{2})")

# =====================
# Base R equivalents
# =====================
grep("hello", text, value = TRUE)
gsub("hello", "bye", text)
strsplit("a,b,c", ",")
regexpr("hello", text)
""",
    ),
    (
        "r/reading-writing-data.md",
        "r",
        ["read.csv", "read_csv", "write_csv", "readxl", "haven", "readRDS", "saveRDS"],
        "Reading/Writing Data",
        "Base R read.csv/write.csv. readr::read_csv/write_csv for faster parsing with better defaults. readxl for Excel, haven for SPSS/Stata/SAS. readRDS/saveRDS for native R objects.",
        "pattern",
        """# =====================
# CSV files
# =====================

# Base R
df <- read.csv("data.csv", stringsAsFactors = FALSE)
write.csv(df, "output.csv", row.names = FALSE)

# readr (tidyverse) — faster, better defaults
library(readr)
df <- read_csv("data.csv",                # does NOT auto-convert strings to factors
               na = c("", "NA", "NULL"),
               col_types = cols(
                 age = col_double(),
                 name = col_character()
               ))
write_csv(df, "output.csv")
write_csv2(df, "output.csv")              # semicolon separator (EU)

# =====================
# Excel
# =====================
library(readxl)
df <- read_excel("data.xlsx", sheet = 1)
sheets <- excel_sheets("data.xlsx")       # list sheet names

library(writexl)
write_xlsx(df, "output.xlsx")

# =====================
# SAS / SPSS / Stata
# =====================
library(haven)
sas  <- read_sas("data.sas7bdat")
spss <- read_spss("data.sav")
stata <- read_dta("data.dta")
write_dta(stata, "output.dta")

# =====================
# R native format
# =====================
saveRDS(df, "data.rds")
df2 <- readRDS("data.rds")

# Save multiple objects
save(df, df2, file = "data.RData")
load("data.RData")

# =====================
# Other formats
# =====================
# JSON
library(jsonlite)
json <- toJSON(df)
df_from_json <- fromJSON(json)

# Feather (fast, cross-language)
library(feather)
write_feather(df, "data.feather")
df <- read_feather("data.feather")

# Parquet
library(arrow)
write_parquet(df, "data.parquet")
df <- read_parquet("data.parquet")
""",
    ),
    (
        "r/rmarkdown-quarto.md",
        "r",
        ["rmarkdown", "quarto", "yaml", "code-chunks", "inline-r", "rendering", "parameters"],
        "R Markdown / Quarto",
        "R Markdown and Quarto blend prose, code, and output. YAML header controls output format. Code chunks with ```{r}. Inline R with `r expr`. Parameterised reports. Render to HTML/PDF/Word.",
        "pattern",
        """---
title: "My Report"
author: "Data Analyst"
date: "`r Sys.Date()`"
output:
  html_document:
    toc: true
    theme: flatly
  pdf_document:
    toc: true
params:
  data_file: "default.csv"
  threshold: 0.05
---

```{r setup, include=FALSE}
library(tidyverse)
library(knitr)
opts_chunk$set(echo = TRUE, warning = FALSE, message = FALSE)
```

## Introduction

This report analyses data from `r params$data_file`.
The significance threshold is `r params$threshold`.

## Data Loading

```{r data-load}
df <- read_csv(params$data_file)
summary(df)
```

## Analysis

```{r analysis}
model <- lm(value ~ group, data = df)
summary(model)
```

```{r plot}
ggplot(df, aes(x = group, y = value)) +
  geom_boxplot(fill = "steelblue") +
  labs(title = "Values by Group")
```

## Table

```{r table, results='asis'}
kable(anova(model), caption = "ANOVA Table")
```

---

*Rendered on `r Sys.time()`*
""",
    ),
    (
        "r/purrr-functional.md",
        "r",
        ["purrr", "map", "map_dbl", "map_chr", "map_df", "reduce", "keep", "discard", "walk", "compose"],
        "purrr & Functional",
        "purrr provides functional programming tools: map() variants return different types, reduce() accumulates, keep/discard filter, walk() for side-effects, partial() fixes args, compose() chains functions.",
        "pattern",
        """library(purrr)

# =====================
# map variants
# =====================
numbers <- list(1, 2, 3, 4, 5)

map(numbers, ~ .x * 2)                  # list(2, 4, 6, 8, 10)
map_dbl(numbers, ~ .x^2)                # double vector: 1, 4, 9, 16, 25
map_chr(numbers, ~ paste("n =", .x))    # character vector
map_lgl(numbers, ~ .x > 3)              # FALSE FALSE FALSE TRUE TRUE

# map_df — returns a data frame (row-binds results)
map_df(1:3, ~ tibble(id = .x, square = .x^2))

# map2 — iterate over two lists in parallel
map2(1:3, 4:6, ~ .x + .y)              # list(5, 7, 9)

# pmap — iterate over multiple lists
pmap(list(a = 1:3, b = 4:6, c = 7:9), ~ ..1 + ..2 + ..3)

# imap — map with index
imap_chr(c(a = "apple", b = "banana"), ~ paste(.y, .x, sep = ": "))

# =====================
# reduce / accumulate
# =====================
reduce(1:5, `+`)                        # 1+2+3+4+5 = 15
reduce(1:5, ~ .x * .y)                  # factorial: 120
accumulate(1:5, `+`)                    # 1, 3, 6, 10, 15

# =====================
# keep / discard / compact
# =====================
x <- list(1, NULL, 2, NA, 3)
compact(x)                              # remove NULL: list(1, 2, NA, 3)

numbers <- c(1, 2, 3, 4, 5)
keep(numbers, ~ .x > 3)                 # 4, 5
discard(numbers, ~ .x %% 2 == 0)        # 1, 3, 5

# =====================
# walk — side effects only
# =====================
walk(c("a", "b", "c"), print)

# =====================
# partial / compose
# =====================
multiply_by <- function(x, y) x * y
double <- partial(multiply_by, y = 2)
double(5)                               # 10

add_one <- ~ .x + 1
square <- ~ .x^2
add_one_then_square <- compose(square, add_one)
add_one_then_square(3)                  # (3+1)^2 = 16

# =====================
# Practical: model fitting with map
# =====================
mtcars %>%
  split(.$cyl) %>%
  map(~ lm(mpg ~ wt, data = .x)) %>%
  map_df(broom::tidy, .id = "cyl")
""",
    ),
    (
        "r/factors-forcats.md",
        "r",
        ["forcats", "factors", "fct_reorder", "fct_relevel", "fct_lump", "fct_infreq", "ordered"],
        "Factors & Forcats",
        "forcats (tidyverse) makes factor manipulation easy. fct_reorder reorders by another variable, fct_relevel moves levels, fct_lump collapses rare levels, fct_infreq orders by frequency, ordered factors.",
        "pattern",
        """library(forcats)
library(ggplot2)
library(dplyr)

# =====================
# Factor creation
# =====================
colors <- factor(c("red", "blue", "green", "blue", "red"))
levels(colors)   # "blue" "green" "red"

# Explicit level ordering
colors <- factor(c("red", "blue", "green"),
                 levels = c("red", "green", "blue"))

# =====================
# fct_relevel — reorder manually
# =====================
fct_relevel(colors, "blue", after = 0)
fct_relevel(colors, "red", after = Inf)

# =====================
# fct_infreq — order by frequency
# =====================
sizes <- factor(c("M", "L", "S", "M", "L", "M", "XL"))
fct_infreq(sizes) |> table()

# =====================
# fct_reorder — reorder by another variable
# =====================
df <- tibble(
  region = factor(c("North", "South", "East", "West",
                     "North", "South", "East", "West")),
  sales  = c(100, 200, 150, 180, 90, 210, 140, 190)
)

df %>%
  mutate(region = fct_reorder(region, sales, .fun = median)) %>%
  ggplot(aes(x = region, y = sales)) +
  geom_boxplot()

# =====================
# fct_lump — lump rare levels together
# =====================
grades <- factor(c(rep("A", 50), rep("B", 30), rep("C", 15),
                   rep("D", 3), rep("F", 2)))
fct_lump(grades, n = 3)        # keep top 3, rest -> "Other"
fct_lump(grades, prop = 0.1)   # keep levels with >= 10% of total
fct_lump_min(grades, min = 10) # keep levels with count >= 10

# =====================
# fct_recode — rename factor levels
# =====================
x <- factor(c("a", "b", "c"))
fct_recode(x, apple = "a", banana = "b")

# =====================
# Ordered factors
# =====================
ordered(c("low", "medium", "high"),
        levels = c("low", "medium", "high"))

# =====================
# Other useful
# =====================
fct_drop(colors)
fct_expand(colors, "yellow")
fct_collapse(colors,
             warm = c("red", "orange"),
             cool = c("blue", "green"))
fct_count(colors)
""",
    ),
    (
        "r/environments-scoping.md",
        "r",
        ["environments", "scoping", "parent.env", "assign", "get", "exists", "ls", "lockEnvironment", "sys.frame"],
        "Environments & Scoping",
        "R uses lexical scoping. Environments are hash maps with a parent pointer. parent.env chains lookups. assign/get for dynamic access. lockEnvironment prevents modification. sys.frame for call frames.",
        "pattern",
        """# =====================
# Environment basics
# =====================
e <- new.env(parent = emptyenv())
e$x <- 42
e$y <- "hello"
assign("z", TRUE, envir = e)

get("x", envir = e)                     # 42
exists("y", envir = e)                  # TRUE
ls(e)                                   # "x" "y" "z"

parent.env(e)                           # emptyenv()
parent.env(globalenv())

# =====================
# Lexical scoping demonstration
# =====================
x <- "global"

f <- function() {
  x <- "local to f"
  g <- function() {
    x <- "local to g"
    x   # returns "local to g"
  }
  g()
}

f()                                     # "local to g"

# =====================
# Closure — function captures its enclosing environment
# =====================
make_counter <- function() {
  count <- 0
  function() {
    count <<- count + 1      # <<- assigns in parent environment
    count
  }
}

counter <- make_counter()
counter()                               # 1
counter()                               # 2

# =====================
# assign / get — dynamic variable access
# =====================
for (i in 1:3) {
  assign(paste0("var_", i), i * 10)
}
var_1                                   # 10
var_2                                   # 20
var_3                                   # 30

# =====================
# lockEnvironment — freeze an environment
# =====================
locked <- new.env()
locked$a <- 1
lockEnvironment(locked)

# =====================
# sys.frame — inspect call stack
# =====================
stack_walk <- function() {
  for (i in sys.nframe():1) {
    cat("Frame", i, ": ", deparse(sys.call(i)), "\\n", sep = "")
  }
}

outer <- function() {
  middle <- function() {
    inner <- function() {
      stack_walk()
    }
    inner()
  }
  middle()
}

outer()
""",
    ),
]
