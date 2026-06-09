---
language: ruby
tags: [architecture, pattern]
title: Modules as Namespaces & Mixins
description: Module nesting, namespace, Enumerable/Comparable custom implementations, Rails Concerns.
source: pattern
---

```ruby
# --- Namespacing ---
module Acme
  module Api
    module V1
      class UsersController
        def index
          'Listing users'
        end
      end
    end
  end
end

controller = Acme::Api::V1::UsersController.new
puts controller.index

# Module with nested constants
module Config
  DEFAULTS = {
    host: 'localhost',
    port: 3000
  }.freeze

  module Database
    ADAPTER = 'postgresql'
  end
end

puts Config::DEFAULTS[:host]        # localhost
puts Config::Database::ADAPTER       # postgresql

# --- Custom Enumerable ---
class Playlist
  include Enumerable

  def initialize(*songs)
    @songs = songs
  end

  def each(&block)
    @songs.each(&block)
  end
end

playlist = Playlist.new('Song A', 'Song B', 'Song C')
puts playlist.map(&:upcase).join(', ')  # SONG A, SONG B, SONG C
puts playlist.first                      # Song A
puts playlist.any? { |s| s.start_with?('A') }  # false

# --- Custom Comparable ---
class Person
  include Comparable

  attr_reader :name, :age

  def initialize(name, age)
    @name = name
    @age = age
  end

  def <=>(other)
    age <=> other.age
  end
end

alice = Person.new('Alice', 30)
bob   = Person.new('Bob', 25)
puts alice > bob   # true
puts [bob, alice].sort.map(&:name).join(', ')  # Bob, Alice

# --- Rails-style Concern ---
# (Pure Ruby equivalent)
module Taggable
  def self.included(base)
    base.extend(ClassMethods)
  end

  module ClassMethods
    def taggable?
      true
    end
  end

  def tags
    @tags ||= []
  end

  def add_tag(tag)
    tags << tag
  end
end

class Article
  include Taggable
end

article = Article.new
article.add_tag('ruby')
puts article.tags.inspect          # ['ruby']
puts Article.taggable?              # true

```
