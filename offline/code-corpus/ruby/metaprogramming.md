---
language: ruby
tags: [meta, pattern]
title: Metaprogramming
description: method_missing, define_method, class_eval, instance_eval, send, respond_to_missing?.
source: pattern
---

```ruby
# --- method_missing ---
class DynamicProxy
  def initialize(target)
    @target = target
  end

  def method_missing(name, *args, &block)
    if @target.respond_to?(name)
      @target.send(name, *args, &block)
    else
      super  # raise NoMethodError
    end
  end

  def respond_to_missing?(name, include_private = false)
    @target.respond_to?(name, include_private) || super
  end
end

proxy = DynamicProxy.new([1, 2, 3])
puts proxy.length  # 3
puts proxy.respond_to?(:length)  # true

# --- define_method ---
class AttributeBuilder
  %i[name email age].each do |attr|
    define_method(attr) do
      instance_variable_get("@#{attr}")
    end

    define_method("#{attr}=") do |value|
      instance_variable_set("@#{attr}", value)
    end
  end
end

obj = AttributeBuilder.new
obj.name = 'Alice'
puts obj.name  # Alice

# --- class_eval / instance_eval ---
class Greeter; end

Greeter.class_eval do
  def hello
    'Hello!'
  end
end

puts Greeter.new.hello  # Hello!

# instance_eval opens the singleton class
obj = 'hello'
obj.instance_eval do
  def shout
    upcase + '!'
  end
end
puts obj.shout  # HELLO!

# --- send (dynamic invocation) ---
method_name = :upcase
puts 'hello'.send(method_name)  # HELLO

# --- Define class methods dynamically ---
class Config
  class << self
    def attr_config(*names)
      names.each do |name|
        define_method(name) do
          instance_variable_get("@#{name}")
        end

        define_method("#{name}=") do |value|
          instance_variable_set("@#{name}", value)
        end
      end
    end
  end

  attr_config :app_name, :version, :debug
end

Config.new.tap do |c|
  c.app_name = 'MyApp'
  c.version = '2.0'
  puts c.app_name  # MyApp
end

```
