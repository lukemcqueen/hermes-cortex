---
language: ruby
tags: [rails, pattern]
title: Ruby on Rails API
description: Rails ActiveRecord, associations, routes, controllers, and serializers for API development.
source: pattern
---

```ruby
# == Models ==
# app/models/user.rb
class User < ApplicationRecord
  has_many :posts, dependent: :destroy

  validates :email, presence: true, uniqueness: true
  validates :name, presence: true

  scope :active, -> { where(active: true) }
  scope :recent, -> { order(created_at: :desc) }
end

# app/models/post.rb
class Post < ApplicationRecord
  belongs_to :user, counter_cache: true

  validates :title, presence: true
  validates :body, presence: true

  scope :published, -> { where(published: true) }
  scope :drafts, -> { where(published: false) }
end

# == Migrations ==
# class CreateUsers < ActiveRecord::Migration[7.1]
#   def change
#     create_table :users do |t|
#       t.string :name, null: false
#       t.string :email, null: false
#       t.boolean :active, default: true
#       t.timestamps
#     end
#     add_index :users, :email, unique: true
#   end
# end

# == Routes ==
# config/routes.rb
# Rails.application.routes.draw do
#   namespace :api do
#     namespace :v1 do
#       resources :users, only: %i[index show create update destroy] do
#         resources :posts, only: %i[index create]
#       end
#     end
#   end
# end

# == Controller ==
# app/controllers/api/v1/users_controller.rb
module Api
  module V1
    class UsersController < ApplicationController
      before_action :set_user, only: %i[show update destroy]

      def index
        users = User.active.recent
        render json: users, each_serializer: UserSerializer
      end

      def show
        render json: @user, serializer: UserSerializer
      end

      def create
        user = User.new(user_params)
        if user.save
          render json: user, serializer: UserSerializer, status: :created
        else
          render json: { errors: user.errors.full_messages }, status: :unprocessable_entity
        end
      end

      private

      def set_user
        @user = User.find(params[:id])
      end

      def user_params
        params.require(:user).permit(:name, :email)
      end
    end
  end
end

# == Serializer (using ActiveModelSerializers or jsonapi-serializer) ==
# class UserSerializer
#   include JSONAPI::Serializer
#
#   attributes :name, :email, :active
#   has_many :posts
# end

```
