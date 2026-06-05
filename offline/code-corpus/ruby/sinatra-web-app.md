---
language: ruby
tags: [web, pattern]
title: Sinatra Web App
description: Sinatra::Base application: routing, params, ERB templates, before/after filters, sessions.
source: pattern
---

```ruby
require 'sinatra/base'
require 'erb'
require 'json'

# Modular Sinatra app (Sinatra::Base)
class MyApp < Sinatra::Base
  # --- Configuration ---
  configure do
    set :sessions, true
    set :session_secret, 'your-secret-here'
    set :show_exceptions, false
    set :views, File.join(__dir__, 'views')
    set :public_folder, File.join(__dir__, 'public')
  end

  # --- Before/After filters ---
  before do
    content_type :html
    @start_time = Time.now
  end

  after do
    elapsed = Time.now - @start_time
    logger.info "Request took #{elapsed}s"
  end

  # --- Routes ---

  get '/' do
    erb :index, locals: { title: 'Home', message: 'Hello, Sinatra!' }
  end

  get '/api/status' do
    content_type :json
    { status: 'ok', time: Time.now.iso8601 }.to_json
  end

  # URL params
  get '/users/:id' do
    "User ##{params[:id]}"
  end

  # Query params
  get '/search' do
    q = params[:q]
    "Search results for: #{q}"
  end

  # Form POST
  post '/users' do
    name = params[:name]
    email = params[:email]
    "Created user #{name} (#{email})"
  end

  # JSON body
  post '/api/users' do
    content_type :json
    data = JSON.parse(request.body.read)
    { id: rand(100), name: data['name'] }.to_json
  end

  # --- Sessions ---
  get '/login' do
    session[:user_id] = params[:id]
    "Logged in as user #{session[:user_id]}"
  end

  get '/logout' do
    session.clear
    'Logged out'
  end

  # --- Error handling ---
  error 404 do
    'Not found'
  end

  error 500 do
    'Internal server error'
  end

  # --- Run if executed directly ---
  run! if app_file == $0
end

# == views/index.erb ==
# <!DOCTYPE html>
# <html>
# <head><title><%= title %></title></head>
# <body>
#   <h1><%= message %></h1>
# </body>
# </html>

```
