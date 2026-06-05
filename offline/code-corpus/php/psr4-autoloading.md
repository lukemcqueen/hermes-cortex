---
language: php
tags: [composer, pattern]
title: PSR-4 Autoloading & Composer
description: Composer autoload configuration, namespaces, and PSR-4 autoloader setup.
source: pattern
---

```php
<?php

// composer.json (typical PSR-4 setup)
// {
//   "name": "acme/app",
//   "autoload": {
//     "psr-4": {
//       "Acme\\App\\": "src/",
//       "Acme\\App\\Tests\\": "tests/"
//     }
//   },
//   "require": {
//     "php": ">=8.1",
//     "guzzlehttp/guzzle": "^7.0"
//   }
// }

// -- src/Models/User.php --
namespace Acme\App\Models;

class User {
    public function __construct(
        public readonly int $id,
        public readonly string $name,
    ) {}
}

// -- src/Services/UserService.php --
namespace Acme\App\Services;

use Acme\App\Models\User;

class UserService {
    /** @var User[] */
    private array $users = [];

    public function addUser(User $user): void {
        $this->users[$user->id] = $user;
    }

    public function findUser(int $id): ?User {
        return $this->users[$id] ?? null;
    }
}

// -- public/index.php (entry point) --
// require __DIR__ . '/../vendor/autoload.php';
//
// use Acme\App\Models\User;
// use Acme\App\Services\UserService;
//
// $service = new UserService();
// $service->addUser(new User(1, 'Alice'));
// echo $service->findUser(1)?->name;

```
