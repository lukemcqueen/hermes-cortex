---
language: ruby
tags: [oop, pattern]
title: Classes & Modules
description: Ruby classes, modules, mixins (include/extend/prepend), attr_accessor, inheritance, super.
source: pattern
---

```ruby
class Animal
  attr_accessor :name

  def initialize(name)
    @name = name
  end

  def speak
    raise NotImplementedError, 'subclasses must implement speak'
  end
end

module Walkable
  def walk
    "#{name} is walking"
  end
end

module Swimmable
  def swim
    "#{name} is swimming"
  end
end

class Dog < Animal
  include Walkable
  include Swimmable

  def speak
    'Woof!'
  end
end

class Cat < Animal
  include Walkable

  def speak
    'Meow!'
  end

  # Prepend example (prepended modules override class methods)
end

module Logger
  def speak
    "[LOG] #{super}"
  end
end

class LoggedCat < Cat
  prepend Logger
end

# Extend adds module methods as class methods
module ClassMethods
  def species
    'Mammal'
  end
end

class Bird < Animal
  extend ClassMethods
end

dog = Dog.new('Rex')
puts dog.speak   # Woof!
puts dog.walk    # Rex is walking
puts dog.swim    # Rex is swimming

cat = LoggedCat.new('Luna')
puts cat.speak   # [LOG] Meow!

puts Bird.species # Mammal

```
