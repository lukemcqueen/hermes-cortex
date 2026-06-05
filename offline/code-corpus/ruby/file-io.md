---
language: ruby
tags: [io, pattern]
title: File I/O
description: File read/write, Dir.glob, CSV parsing, Pathname, Tempfile, IO.popen.
source: pattern
---

```ruby
require 'csv'
require 'pathname'
require 'tempfile'
require 'fileutils'

# --- Basic file reading ---
content = File.read('/path/to/file.txt')
lines   = File.readlines('/path/to/file.txt')

# Line-by-line (memory efficient)
File.foreach('/path/to/large-file.txt') do |line|
  puts line
end

# --- File writing ---
File.write('/path/to/output.txt', 'Hello, World!')

File.open('/path/to/output.txt', 'w') do |f|
  f.puts 'Line 1'
  f.puts 'Line 2'
end

# Append mode
File.open('/path/to/log.txt', 'a') do |f|
  f.puts "New entry at #{Time.now}"
end

# --- CSV ---
CSV.foreach('/path/to/data.csv', headers: true) do |row|
  puts "#{row['Name']}: #{row['Email']}"
end

CSV.open('/path/to/output.csv', 'w') do |csv|
  csv << %w[Name Email Age]
  csv << %w[Alice alice@example.com 30]
  csv << %w[Bob bob@example.com 25]
end

# --- Dir.glob ---
Dir.glob('src/**/*.rb').each { |f| puts f }
Dir.glob(['*.txt', '*.md'])  # multiple patterns
Dir.glob('**/*').select { |f| File.file?(f) }

# --- Pathname ---
path = Pathname.new('/path/to/file.txt')
puts path.basename      # file.txt
puts path.dirname       # /path/to
puts path.extname       # .txt
puts path.join('subdir', 'other.txt')

# --- Tempfile ---
Tempfile.create(%w[prefix .csv]) do |f|
  f.puts 'data'
  f.path  # => /tmp/prefix20260101-1234-abc.csv
end  # auto-deleted

# --- IO.popen ---
IO.popen('ls -la', &:read)  # reads command output

# --- FileUtils ---
FileUtils.mkdir_p('/path/to/nested/dir')
FileUtils.cp('/source.txt', '/dest.txt')
FileUtils.mv('/old.txt', '/new.txt')
FileUtils.rm_rf('/path/to/delete')

```
