---
language: ruby
tags: [collections, pattern]
title: Symbols & Hashes
description: Symbol vs string, Hash#fetch/merge/transform_keys/dig, keyword arguments, ** splat.
source: pattern
---

```ruby
# --- Symbols vs Strings ---
:symbol        # immutable, interned, used as identifiers
'string'       # mutable, different object each time

# Key differences:
puts :hello.object_id == :hello.object_id  # true (same object)
puts 'hello'.object_id == 'hello'.object_id  # false (different objects)

# Common use: hash keys
user = { name: 'Alice', age: 30, admin: true }
user[:name]  # 'Alice'

# --- Hash#fetch (safe key access) ---
config = { host: 'localhost', port: 3000 }

puts config.fetch(:host)                    # 'localhost'
puts config.fetch(:missing, 'default')      # 'default'
puts config.fetch(:missing) { |key| "key #{key} not found" }
# config.fetch(:missing)                    # KeyError!

# --- Hash#merge ---
defaults = { host: 'localhost', port: 80 }
overrides = { port: 3000, debug: true }

merged = defaults.merge(overrides)
# { host: 'localhost', port: 3000, debug: true }

# Merge with block for conflict resolution
merged = defaults.merge(overrides) { |_key, old, new| old }
# { host: 'localhost', port: 80, debug: true }

# --- Hash#transform_keys ---
old_hash = { 'name' => 'Alice', 'age' => 30 }
new_hash = old_hash.transform_keys(&:to_sym)
# { name: 'Alice', age: 30 }

# --- Hash#dig (deep access, Ruby 2.3+) ---
data = {
  user: {
    profile: {
      name: 'Alice',
      address: { city: 'NYC' }
    }
  }
}

puts data.dig(:user, :profile, :name)         # 'Alice'
puts data.dig(:user, :profile, :address, :city) # 'NYC'
puts data.dig(:user, :missing, :key)           # nil (no error)

# --- Keyword arguments ---
def greet(name:, greeting: 'Hello', punctuation: '!')
  "#{greeting}, #{name}#{punctuation}"
end

puts greet(name: 'Alice')                       # Hello, Alice!
puts greet(name: 'Bob', greeting: 'Hi')         # Hi, Bob!

# --- ** splat (double splat) ---
def create_user(**attrs)
  # attrs is a Hash
  puts "Creating user with: #{attrs.inspect}"
end

create_user(name: 'Alice', role: 'admin')

# Merge keyword args with defaults
def configure(host:, port: 8080, **extras)
  puts "Host: #{host}, Port: #{port}"
  puts "Extra: #{extras}" unless extras.empty?
end

configure(host: 'example.com', port: 3000, debug: true, ssl: true)
# Host: example.com, Port: 3000
# Extra: {:debug=>true, :ssl=>true}

# --- Hash to keyword args ---
params = { name: 'Alice', age: 30 }
# some_method(**params)  # expands hash into keyword args

```
