---
language: php
tags: [auth, pattern]
title: Sessions & Cookies
description: Session management, cookie handling, flash messages, and CSRF token pattern.
source: pattern
---

```php
<?php

// --- Session Configuration ---
ini_set('session.use_strict_mode', 1);
ini_set('session.use_only_cookies', 1);
ini_set('session.cookie_httponly', 1);
ini_set('session.cookie_samesite', 'Lax');
session_set_cookie_params([
    'lifetime' => 7200,
    'path'     => '/',
    'domain'   => '',
    'secure'   => true,
    'httponly' => true,
    'samesite' => 'Lax',
]);

session_start();

// --- Flash messages ---
function setFlash(string $type, string $message): void {
    $_SESSION['_flash'][] = ['type' => $type, 'message' => $message];
}

function getFlashes(): array {
    $flashes = $_SESSION['_flash'] ?? [];
    unset($_SESSION['_flash']);
    return $flashes;
}

// --- CSRF Token ---
if (empty($_SESSION['_csrf_token'])) {
    $_SESSION['_csrf_token'] = bin2hex(random_bytes(32));
}

function csrfToken(): string {
    return $_SESSION['_csrf_token'];
}

function csrfField(): string {
    return '<input type="hidden" name="_csrf_token" value="' . csrfToken() . '">';
}

function verifyCsrf(?string $token): bool {
    return hash_equals($_SESSION['_csrf_token'] ?? '', $token ?? '');
}

// --- Cookie handling ---
setcookie('preferences', json_encode(['theme' => 'dark']), [
    'expires'  => time() + 86400 * 30,
    'path'     => '/',
    'secure'   => true,
    'httponly' => true,
    'samesite' => 'Lax',
]);

$prefs = json_decode($_COOKIE['preferences'] ?? '{}', true);

// --- Login example ---
// if (password_verify($password, $user['password_hash'])) {
//     session_regenerate_id(true);
//     $_SESSION['user_id'] = $user['id'];
//     setFlash('success', 'Welcome back!');
//     header('Location: /dashboard');
//     exit;
// }

```
