---
language: php
tags: [database, pattern]
title: PDO Database
description: PDO connection, prepared statements, fetch modes, transactions, and error handling.
source: pattern
---

```php
<?php

$dsn = 'mysql:host=127.0.0.1;port=3306;dbname=app;charset=utf8mb4';
$username = 'root';
$password = 'secret';
$options = [
    PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES   => false,
];

try {
    $pdo = new PDO($dsn, $username, $password, $options);
} catch (PDOException $e) {
    die('Connection failed: ' . $e->getMessage());
}

// Prepared statement (SELECT)
$stmt = $pdo->prepare('SELECT id, name, email FROM users WHERE active = :active');
$stmt->execute([':active' => 1]);
$users = $stmt->fetchAll();

// Prepared statement (INSERT)
$stmt = $pdo->prepare(
    'INSERT INTO users (name, email, active) VALUES (:name, :email, :active)'
);
$stmt->execute([
    ':name'   => 'Alice',
    ':email'  => 'alice@example.com',
    ':active' => 1,
]);
$newId = $pdo->lastInsertId();

// Transactions
try {
    $pdo->beginTransaction();
    $pdo->exec('UPDATE accounts SET balance = balance - 100 WHERE id = 1');
    $pdo->exec('UPDATE accounts SET balance = balance + 100 WHERE id = 2');
    $pdo->commit();
} catch (PDOException $e) {
    $pdo->rollBack();
    error_log('Transfer failed: ' . $e->getMessage());
}

// Named vs positional placeholders
$stmt = $pdo->prepare('SELECT * FROM users WHERE id = ?');
$stmt->execute([42]);
$user = $stmt->fetch();

// Row count
$count = $stmt->rowCount();

```
