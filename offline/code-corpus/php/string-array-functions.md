---
language: php
tags: [utility, pattern]
title: String & Array Functions
description: Essential PHP string and array manipulation: str_replace, preg_match, array_map/filter/reduce.
source: pattern
---

```php
<?php

// --- String functions ---
$text = 'Hello, World!';

echo str_replace('World', 'PHP', $text);        // Hello, PHP!
echo str_contains($text, 'World');              // true (PHP 8.0+)
echo str_starts_with($text, 'Hello');           // true (PHP 8.0+)
echo str_ends_with($text, '!');                 // true (PHP 8.0+)

preg_match('/(\\w+), (\\w+)!/', $text, $matches);
echo $matches[1];  // Hello

$newText = preg_replace('/(\\w+)/e', 'strtoupper($1)', $text); // (modern: use preg_replace_callback)
$upper    = preg_replace_callback('/\\w+/', fn($m) => strtoupper($m[0]), $text);
echo $upper;  // HELLO, WORLD!

// --- Array functions ---
$numbers = [1, 2, 3, 4, 5];

$doubled = array_map(fn(int $n): int => $n * 2, $numbers);
// [2, 4, 6, 8, 10]

$evens = array_filter($numbers, fn(int $n): bool => $n % 2 === 0);
// [2, 4]

$sum = array_reduce($numbers, fn(int $carry, int $n): int => $carry + $n, 0);
// 15

$keys   = ['a', 'b', 'c'];
$values = [1, 2, 3];
$combined = array_combine($keys, $values);
// ['a' => 1, 'b' => 2, 'c' => 3]

$merged = array_merge(['x' => 1], ['y' => 2]);
// ['x' => 1, 'y' => 2]

$diff = array_diff([1, 2, 3, 4], [2, 4]);
// [1, 3]

$intersect = array_intersect([1, 2, 3], [2, 3, 4]);
// [2, 3]

// Chunk
$chunks = array_chunk(range(1, 10), 3);
// [[1,2,3], [4,5,6], [7,8,9], [10]]

// Column (extract column from multi-dimensional array)
$users = [
    ['id' => 1, 'name' => 'Alice'],
    ['id' => 2, 'name' => 'Bob'],
];
$names = array_column($users, 'name');
// ['Alice', 'Bob']

```
