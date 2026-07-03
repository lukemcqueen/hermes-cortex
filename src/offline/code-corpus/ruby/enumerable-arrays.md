---
language: ruby
tags: [collections, pattern]
title: Enumerable & Arrays
description: Ruby Enumerable module: map/select/reduce, each_with_object, group_by, lazy enumerators.
source: pattern
---

```ruby
# --- Core Enumerable methods ---
numbers = [1, 2, 3, 4, 5, 6]

doubled = numbers.map { |n| n * 2 }
# [2, 4, 6, 8, 10, 12]

evens = numbers.select(&:even?)
# [2, 4, 6]

odds = numbers.reject(&:even?)
# [1, 3, 5]

sum = numbers.reduce(0) { |acc, n| acc + n }
# 21
sum = numbers.sum          # 21 (Ruby 2.4+)

product = numbers.reduce(1, :*)
# 720

# --- each_with_object ---
grouped = numbers.each_with_object({}) do |n, hash|
  hash[n.even? ? 'even' : 'odd'] ||= []
  hash[n.even? ? 'even' : 'odd'] << n
end
# {'odd' => [1, 3, 5], 'even' => [2, 4, 6]}

# --- group_by ---
words = %w[apple ant bear cat dog elephant]
by_first_letter = words.group_by { |w| w[0] }
# {'a' => ['apple', 'ant'], 'b' => ['bear'], 'c' => ['cat'], 'd' => ['dog'], 'e' => ['elephant']}

# --- sort_by ---
sorted = words.sort_by(&:length)
# ['ant', 'cat', 'dog', 'bear', 'apple', 'elephant']

# --- chunk ---
chunks = [1, 1, 2, 2, 2, 3, 1, 1].chunk(&:itself).to_a
# [[1, [1, 1]], [2, [2, 2, 2]], [3, [3]], [1, [1, 1]]]

# --- Lazy enumerators ---
lazy = (1..Float::INFINITY).lazy
  .map { |n| n * n }
  .select(&:even?)
  .first(5)
# [4, 16, 36, 64, 100]

# --- Custom Enumerable ---
class Fibonacci
  include Enumerable

  def each
    a, b = 0, 1
    loop do
      yield a
      a, b = b, a + b
    end
  end
end

Fibonacci.new.first(10)  # [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]

```
