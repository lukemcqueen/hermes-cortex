---
language: ruby
tags: [utility, pattern]
title: Strings & Regex
description: String manipulation: gsub, scan, match, split, %w/%i literals, interpolation, squish, humanize.
source: pattern
---

```ruby
# --- String literals ---
name = 'Alice'
double_quote = "Hello, #{name}!"         # interpolation
single_quote = 'Hello, #{name}!'         # literal

# %w / %i literals
words = %w[apple banana cherry]           # ['apple', 'banana', 'cherry']
syms  = %i[red green blue]               # [:red, :green, :blue]
multi = <<~TEXT
  Multiline
  string
TEXT

# --- gsub (global substitution) ---
text = 'Hello, World!'
puts text.gsub('World', 'Ruby')          # Hello, Ruby!
puts text.gsub(/[aeiou]/i, '*')          # H*ll*, W*rld!
puts text.gsub(/[A-Z]/) { |c| "[#{c}]" } # [H]ello, [W]orld!

# --- scan ---
numbers = 'abc123def456ghi789'
puts numbers.scan(/\\d+/).inspect        # ['123', '456', '789']
pairs   = 'a=1,b=2,c=3'.scan(/(\\w)=(\\d)/)
# [['a', '1'], ['b', '2'], ['c', '3']]

# --- match ---
match = 'user@example.com'.match(/\\A(\\w+)@(.+)\\z/)
if match
  puts match[1]  # user
  puts match[2]  # example.com
end

# Named captures
m = '2026-06-05'.match(/(?<year>\\d{4})-(?<month>\\d{2})-(?<day>\\d{2})/)
puts m[:year]   # 2026

# --- split ---
csv = 'a,b,c,d'
puts csv.split(',').inspect               # ['a', 'b', 'c', 'd']
sentence = 'Hello   World!'
puts sentence.split.inspect                # ['Hello', 'World!']
puts sentence.split(/\\s+/, 2).inspect   # ['Hello', 'World!']

# --- ActiveSupport-style methods (require 'active_support/core_ext') ---
# require 'active_support/core_ext'
# puts 'hello_world'.humanize  # 'Hello world'
# puts '  lots   of   space '.squish  # 'lots of space'
# puts 'hello'.titleize  # 'Hello'
# puts 'User'.pluralize  # 'Users'

# --- Other useful string methods ---
'hello'.capitalize   # 'Hello'
'HELLO'.downcase     # 'hello'
'hello'.upcase       # 'HELLO'
'  hi  '.strip       # 'hi'
'hello'.reverse      # 'olleh'
'hello'.ljust(10)    # 'hello     '
'hello'.rjust(10)    # '     hello'
'42'.to_i            # 42
'3.14'.to_f          # 3.14

```
