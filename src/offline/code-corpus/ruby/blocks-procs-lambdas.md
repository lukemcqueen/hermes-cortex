---
language: ruby
tags: [functional, pattern]
title: Blocks, Procs & Lambdas
description: Blocks (yield, block_given?), Proc.new, lambda, &block conversion, Symbol#to_proc.
source: pattern
---

```ruby
# --- Blocks ---
def timer
  start = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  yield if block_given?
  finish = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  "Elapsed: #{finish - start}s"
end

result = timer { sleep(0.1) }
puts result  # Elapsed: ~0.1s

# Block with arguments
def each_item(array)
  array.each_with_index { |item, idx| yield(item, idx) }
end

each_item(%w[a b c]) do |item, idx|
  puts "#{idx}: #{item}"
end

# --- Proc ---
# Procs don't enforce arity (unlike lambdas)
double = proc { |x| x * 2 }
puts double.call(5)         # 10
puts double.call(5, 10)     # 10 (extra arg ignored)

# --- Lambda ---
# Lambdas DO enforce arity
square = ->(x) { x * x }
puts square.call(4)         # 16
# square.call(1, 2) would raise ArgumentError

# Lambda with multiple args
add = ->(a, b) { a + b }
puts add.call(3, 4)         # 7

# --- &block conversion ---
def method_with_block(&block)
  block.call('from method')
end

method_with_block { |msg| puts msg }

# Passing a proc as a block
my_proc = proc { |n| n ** 2 }
[1, 2, 3].map(&my_proc)    # [1, 4, 9]

# Symbol#to_proc
puts %w[alice bob charlie].map(&:capitalize).join(', ')
# Alice, Bob, Charlie

[10, 20, 30].map(&:to_s)   # ['10', '20', '30']

# --- Proc vs Lambda differences ---
def proc_return
  p = proc { return 'proc return' }
  p.call
  'never reached'
end

def lambda_return
  l = -> { return 'lambda return' }
  l.call
  'after lambda'
end

puts proc_return   # proc return (return exits the enclosing method)
puts lambda_return # after lambda (return just exits the lambda)

```
