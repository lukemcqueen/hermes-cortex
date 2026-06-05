---
language: php
tags: [security, pattern]
title: Security
description: Password hashing/verification, XSS prevention, input filtering, SQL injection prevention, CSRF.
source: pattern
---

```php
<?php

// --- Password Hashing ---
$password = 's3cret!';
$hash = password_hash($password, PASSWORD_BCRYPT, ['cost' => 12]);
// Store $hash in database

if (password_verify($password, $hash)) {
    echo 'Password is valid!';
}

// Check if rehashing is needed
if (password_needs_rehash($hash, PASSWORD_BCRYPT, ['cost' => 13])) {
    $newHash = password_hash($password, PASSWORD_BCRYPT, ['cost' => 13]);
    // Update stored hash
}

// --- XSS Prevention ---
$userInput = '<script>alert("xss")</script>';
$safe = htmlspecialchars($userInput, ENT_QUOTES | ENT_HTML5, 'UTF-8');
echo $safe;
// &lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;

// --- Input Filtering ---
$email = filter_input(INPUT_POST, 'email', FILTER_VALIDATE_EMAIL);
$age   = filter_input(INPUT_POST, 'age', FILTER_VALIDATE_INT, [
    'options' => ['min_range' => 1, 'max_range' => 150],
]);
$url   = filter_input(INPUT_GET, 'redirect', FILTER_VALIDATE_URL);

// Sanitization
$name      = filter_var($rawName, FILTER_SANITIZE_STRING);
$cleanHtml = strip_tags($rawHtml, '<p><a><br>');

// --- SQL Injection Prevention (with PDO prepared statements) ---
$stmt = $pdo->prepare('SELECT * FROM users WHERE email = :email AND active = :active');
$stmt->execute([':email' => $email, ':active' => 1]);

// Never: $pdo->query("SELECT * FROM users WHERE id = {$_GET['id']}");

// --- CSRF Prevention (token pattern) ---
session_start();
if (empty($_SESSION['_token'])) {
    $_SESSION['_token'] = bin2hex(random_bytes(32));
}

function csrf_token(): string {
    return $_SESSION['_token'];
}

function verify_token(string $token): bool {
    return hash_equals($_SESSION['_token'], $token);
}

// In form: <input type="hidden" name="_token" value="<?= csrf_token() ?>">
// On submit: if (!verify_token($_POST['_token'] ?? '')) { die('CSRF detected'); }

// --- Output encoding context matters ---
// HTML: htmlspecialchars($data, ENT_QUOTES, 'UTF-8')
// JS: json_encode($data)
// URL: rawurlencode($data)
// CSS: not recommended to embed user input

```
