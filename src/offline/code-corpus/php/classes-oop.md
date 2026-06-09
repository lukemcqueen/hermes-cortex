---
language: php
tags: [oop, pattern]
title: Classes & OOP
description: PHP 8.x object-oriented features: readonly properties, constructor promotion, enums, interfaces, traits.
source: pattern
---

```php
<?php

// Readonly class with constructor promotion (PHP 8.1+)
readonly class User {
    public function __construct(
        public string $name,
        public string $email,
        public Address $address,
    ) {}
}

// Enum (PHP 8.1+)
enum Role: string {
    case Admin = 'admin';
    case Editor = 'editor';
    case Viewer = 'viewer';
}

// Interface
interface Notifiable {
    public function notify(string $message): void;
}

// Trait
trait ValidatesEmail {
    public function isValidEmail(string $email): bool {
        return filter_var($email, FILTER_VALIDATE_EMAIL) !== false;
    }
}

// Class implementing interface, using trait
class AdminUser extends User implements Notifiable {
    use ValidatesEmail;

    public function __construct(
        string $name,
        string $email,
        Address $address,
        public Role $role = Role::Admin,
    ) {
        parent::__construct($name, $email, $address);
    }

    public function notify(string $message): void {
        if ($this->isValidEmail($this->email)) {
            mail($this->email, 'Notification', $message);
        }
    }
}

$user = new AdminUser('Alice', 'alice@example.com', new Address('123 Main St'));
echo $user->name; // Alice

```
