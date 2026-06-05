---
language: ruby
tags: [concurrency, pattern]
title: Concurrency
description: Thread, Mutex, Queue, Fiber, Concurrent::Future from concurrent-ruby gem.
source: pattern
---

```ruby
require 'concurrent'  # gem 'concurrent-ruby'

# --- Thread basics ---
threads = []
results = []

mutex = Mutex.new

5.times do |i|
  threads << Thread.new(i) do |n|
    sleep(rand * 0.1)
    mutex.synchronize do
      results << n * 2
    end
  end
end

threads.each(&:join)
puts results.sort.inspect  # [0, 2, 4, 6, 8]

# --- Thread pool via Queue ---
queue = Queue.new
workers = 4.times.map do
  Thread.new do
    until (item = queue.pop(true) rescue nil).nil?
      sleep(0.05)
      puts "Processed #{item}"
    end
  end
end

(1..20).each { |i| queue << i }
queue.close
workers.each(&:join)

# --- Fiber (cooperative concurrency) ---
fiber = Fiber.new do
  puts 'Fiber: step 1'
  Fiber.yield
  puts 'Fiber: step 2'
end

puts 'Main: before resume'
fiber.resume
puts 'Main: between resumes'
fiber.resume
puts 'Main: done'

# --- Concurrent::Future (from concurrent-ruby) ---
futures = 5.times.map do |i|
  Concurrent::Future.execute do
    sleep(rand * 0.2)
    i ** 2
  end
end

# Block until all complete
values = futures.map(&:value!)
puts values.sort.inspect  # [0, 1, 4, 9, 16]

# --- Concurrent::Promise chain ---
promise = Concurrent::Promise.new { 42 }
  .then { |v| v * 2 }
  .then { |v| "Answer: #{v}" }
  .execute

puts promise.value!  # Answer: 84

# --- Actor-like pattern with concurrent-ruby ---
class Counter
  def initialize
    @count = 0
    @mutex = Mutex.new
  end

  def increment
    @mutex.synchronize { @count += 1 }
  end

  def value
    @mutex.synchronize { @count }
  end
end

counter = Counter.new
10.times.map { Thread.new { 100.times { counter.increment } } }.each(&:join)
puts counter.value  # 1000

```
