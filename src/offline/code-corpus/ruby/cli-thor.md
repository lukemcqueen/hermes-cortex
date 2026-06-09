---
language: ruby
tags: [cli, pattern]
title: CLI & Thor
description: ARGV, OptionParser, Thor CLI framework: subcommands, options, defaults.
source: pattern
---

```ruby
require 'optparse'
require 'thor'

# --- ARGV basics ---
# Run: ruby script.rb --name=Alice --verbose
name    = ARGV[0] || 'World'
verbose = ARGV.include?('--verbose')
puts "Hello, #{name}!"
puts 'Verbose mode' if verbose

# --- OptionParser ---
params = {}
OptionParser.new do |opts|
  opts.banner = 'Usage: script.rb [options]'

  opts.on('-n', '--name NAME', 'Name to greet') do |n|
    params[:name] = n
  end

  opts.on('-v', '--[no-]verbose', 'Run verbosely') do |v|
    params[:verbose] = v
  end

  opts.on('-c', '--count N', Integer, 'Repeat count') do |c|
    params[:count] = c
  end

  opts.on('-h', '--help', 'Show help') do
    puts opts
    exit
  end
end.parse!

name = params[:name] || 'World'
puts "Hello, #{name}!" * (params[:count] || 1)

# --- Thor CLI (gem install thor) ---
class MyCLI < Thor
  desc 'hello NAME', 'Greet someone'
  option :yell, type: :boolean, aliases: '-y', desc: 'Yell the greeting'
  option :repeat, type: :numeric, default: 1, aliases: '-r'
  def hello(name = 'World')
    greeting = "Hello, #{name}!"
    greeting = greeting.upcase if options[:yell]
    options[:repeat].times { puts greeting }
  end

  desc 'serve', 'Start the server'
  option :port, type: :numeric, default: 3000, aliases: '-p'
  option :env, type: :string, default: 'development', aliases: '-e'
  def serve
    puts "Starting server on port #{options[:port]} (#{options[:env]} env)"
    # Server start logic here
  end

  desc 'generate TYPE NAME', 'Generate a scaffold'
  subcommand 'generate', GenerateCommands

  method_option :force, type: :boolean, aliases: '-f', desc: 'Overwrite existing files'
  def scaffold(name)
    puts "Generating scaffold for #{name}"
  end

  # Default task
  default_task :hello
end

# Subcommand class
class GenerateCommands < Thor
  desc 'model NAME', 'Generate a model'
  option :fields, type: :array, aliases: '-f'
  def model(name)
    fields = (options[:fields] || %w[name email]).join(', ')
    puts "Generating model #{name} with fields: #{fields}"
  end

  desc 'controller NAME', 'Generate a controller'
  option :actions, type: :array, aliases: '-a', default: %w[index show]
  def controller(name)
    puts "Generating #{name} controller with actions: #{options[:actions].join(', ')}"
  end
end

# To run:
#   ruby script.rb hello Alice --yell
#   ruby script.rb help
#   ruby script.rb serve --port=4567
#   ruby script.rb generate model User --fields name email age

```
