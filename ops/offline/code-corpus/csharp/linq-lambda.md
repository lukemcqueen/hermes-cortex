---
language: csharp
tags: [csharp, linq, lambda, deferred-execution, query-syntax]
title: LINQ & Lambda Expressions
description: Method-syntax and query-syntax LINQ, deferred execution with IEnumerable, GroupBy, Aggregate, and Any/All checks.
source: pattern
---

```csharp
var numbers = Enumerable.Range(1, 100);

// Method syntax — fluent
var result = numbers
    .Where(n => n % 3 == 0)
    .OrderByDescending(n => n)
    .Select(n => new { Original = n, Squared = n * n })
    .Take(5)
    .ToList();

// Query syntax (expression tree equivalent)
var query = from n in numbers
            where n % 3 == 0
            orderby n descending
            select new { Original = n, Squared = n * n };

// GroupBy
var grouped = numbers.GroupBy(n => n % 2 == 0 ? "Even" : "Odd");

// Aggregate (fold)
int sum = numbers.Aggregate(0, (acc, n) => acc + n);

// Any / All
bool hasPrimes = numbers.Any(n => n is 2 or 3 or 5 or 7);
bool allPositive = numbers.All(n => n > 0);

// Deferred execution (IEnumerable is lazy; ToList/ToArray materialises)
IEnumerable<int> deferred = numbers.Where(n => n > 50);   // not executed yet
var materialised = deferred.ToList();                     // executed now

```
