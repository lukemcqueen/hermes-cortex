---
language: php
tags: [laravel, pattern]
title: Laravel Eloquent
description: Eloquent ORM: model definitions, relationships, scopes, accessors, mutators, eager loading.
source: pattern
---

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class User extends Model
{
    // Relationships
    public function posts(): HasMany
    {
        return $this->hasMany(Post::class);
    }

    // Accessor
    public function getFullNameAttribute(): string
    {
        return "{$this->first_name} {$this->last_name}";
    }

    // Mutator
    public function setPasswordAttribute(string $value): void
    {
        $this->attributes['password'] = bcrypt($value);
    }

    // Local scope
    public function scopeActive(Builder $query): Builder
    {
        return $query->where('active', true);
    }

    public function scopeVip(Builder $query): Builder
    {
        return $query->where('vip', true);
    }
}

class Post extends Model
{
    protected $fillable = ['title', 'content', 'user_id'];

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    // Global scope example
    protected static function booted(): void
    {
        static::addGlobalScope('published', function (Builder $builder) {
            $builder->where('published', true);
        });
    }
}

// -- Migrations --
// use Illuminate\Database\Migrations\Migration;
// use Illuminate\Database\Schema\Blueprint;
// use Illuminate\Support\Facades\Schema;
//
// return new class extends Migration {
//     public function up(): void {
//         Schema::create('posts', function (Blueprint $table) {
//             $table->id();
//             $table->foreignId('user_id')->constrained()->cascadeOnDelete();
//             $table->string('title');
//             $table->text('content');
//             $table->boolean('published')->default(false);
//             $table->timestamps();
//         });
//     }
// };

// -- Usage --
// $vipUsers = User::active()->vip()->with('posts')->get();
// foreach ($vipUsers as $user) {
//     echo "{$user->full_name}: {$user->posts->count()} posts\n";
// }

```
