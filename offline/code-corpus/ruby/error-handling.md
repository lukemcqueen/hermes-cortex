---
language: ruby
tags: [error, pattern]
title: Error Handling
description: Ruby exception handling: begin/rescue/ensure/else, custom exceptions, retry, StandardError.
source: pattern
---

```ruby
# --- Basic error handling ---
begin
  result = 10 / 0
rescue ZeroDivisionError => e
  puts "Caught: #{e.message}"
rescue TypeError => e
  puts "Type error: #{e.message}"
else
  puts "No error occurred, result is #{result}"
ensure
  puts 'This always runs (cleanup)'
end

# --- Custom exceptions ---
class AppError < StandardError; end
class ValidationError < AppError; end
class NotFoundError < AppError; end

def find_user(id)
  raise NotFoundError, "User #{id} not found" if id.nil? || id <= 0
  { id: id, name: 'Alice' }
end

begin
  find_user(nil)
rescue ValidationError => e
  puts "Validation: #{e.message}"
rescue NotFoundError => e
  puts "Not found: #{e.message}"
rescue AppError => e
  puts "App error: #{e.message}"
end

# --- Retry ---
attempts = 0
begin
  attempts += 1
  puts "Attempt #{attempts}"
  raise 'temporary failure' if attempts < 3
rescue StandardError => e
  puts "Failed: #{e.message}"
  retry if attempts < 3
end

# --- Ensure with early return ---
def risky_operation
  file = File.open('/tmp/test.txt', 'w')
  return 'done'  # ensure still runs
ensure
  file&.close
  puts 'File closed'
end

puts risky_operation

# --- Rescue inline ---
value = risky_method rescue 'default'
# (catches any StandardError)

# --- Exception hierarchy ---
# StandardError
#   +-- RuntimeError
#   +-- ArgumentError
#   +-- NameError
#   +-- NoMethodError
#   +-- TypeError
#   +-- ZeroDivisionError
#
# Exception (top-level, rarely rescue directly)
#   +-- SystemExit
#   +-- SignalException
#   +-- NoMemoryError

```
