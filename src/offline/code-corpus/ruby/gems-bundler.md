---
language: ruby
tags: [dependencies, pattern]
title: Gems & Bundler
description: Gemfile, gemspec, bundler setup, require, version constraints, Rake tasks.
source: pattern
---

```ruby
# == Gemfile ==
# source 'https://rubygems.org'
#
# ruby '>= 3.1'
#
# gem 'rails', '~> 7.1'
# gem 'pg', '~> 1.5'
# gem 'puma', '>= 6.0'
# gem 'bootsnap', require: false
#
# group :development, :test do
#   gem 'rspec-rails', '~> 6.0'
#   gem 'factory_bot_rails'
#   gem 'rubocop', require: false
# end
#
# group :development do
#   gem 'better_errors'
#   gem 'binding_of_caller'
# end
#
# group :test do
#   gem 'shoulda-matchers'
#   gem 'database_cleaner-active_record'
# end
#
# gem 'rack-cors', '~> 2.0'

# == Bundler setup ==
# require 'bundler/setup'
# Bundler.require(:default, :development)

# == .gemspec (for gem development) ==
# Gem::Specification.new do |spec|
#   spec.name          = 'my_gem'
#   spec.version       = '0.1.0'
#   spec.authors       = ['Alice']
#   spec.email         = ['alice@example.com']
#   spec.summary       = 'A summary'
#   spec.description   = 'A longer description'
#   spec.license       = 'MIT'
#
#   spec.required_ruby_version = '>= 3.1'
#
#   spec.files = Dir['lib/**/*.rb'] + %w[README.md LICENSE]
#
#   spec.add_dependency 'faraday', '~> 2.0'
#   spec.add_development_dependency 'rspec', '~> 3.12'
# end

# == Version constraints ==
# gem 'nokogiri', '>= 1.14', '< 2.0'
# gem 'sidekiq', '~> 7.0'    # >= 7.0, < 8.0
# gem 'redis',  '~> 5.0.0'   # >= 5.0.0, < 5.1.0

# == Rake tasks ==
# require 'bundler/gem_tasks'
# require 'rspec/core/rake_task'
#
# RSpec::Core::RakeTask.new(:spec)
# task default: :spec

# == Using bundler inline (without Gemfile) ==
# require 'bundler/inline'
#
# gemfile do
#   source 'https://rubygems.org'
#   gem 'json'
#   gem 'httparty'
# end

```
