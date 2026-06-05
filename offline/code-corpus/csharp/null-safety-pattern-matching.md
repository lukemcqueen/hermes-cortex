---
language: csharp
tags: [csharp, null-safety, nullable, pattern-matching, switch-expression]
title: Null Safety & Pattern Matching
description: Nullable reference types, null-forgiving operator, null-conditional ?., switch expressions, property patterns, list patterns, and relational patterns.
source: pattern
---

```csharp
#nullable enable

// ── Nullable reference types ───────────────────────────────────────────
public class Customer
{
    public string Name { get; set; }           // required — non-nullable
    public string? MiddleName { get; set; }    // optional — nullable
    public Address? ShippingAddress { get; set; }

    public string GetDisplayName() =>
        $"{Name}{(MiddleName is not null ? $" {MiddleName}" : "")}";
}

// Null-conditional (?.)
string? city = customer?.ShippingAddress?.City;

// Null-forgiving (!) — use only when you know it's safe
int length = customer.Name!.Length;

// ── Switch expression ──────────────────────────────────────────────────
string Describe(int? value) => value switch
{
    null  => "no value",
    < 0   => "negative",
    >= 0 and < 10 => "small",
    >= 10 and < 100 => "medium",
    _     => "large"
};

// ── Property patterns ──────────────────────────────────────────────────
static decimal CalculateDiscount(Product product) => product switch
{
    { Category: "Electronics", Price: > 1000 } => 0.10m,
    { Category: "Books", IsOnSale: true }      => 0.15m,
    { Price: < 5 }                             => 0.05m,
    _                                          => 0m
};

// ── List patterns (C# 11) ──────────────────────────────────────────────
int[] numbers = { 1, 2, 3, 4 };
string MatchList(int[] arr) => arr switch
{
    []          => "empty",
    [var first] => $"one element: {first}",
    [1, ..]     => "starts with 1",
    [_, _, ..]  => "at least two elements",
    _           => "other"
};

```
