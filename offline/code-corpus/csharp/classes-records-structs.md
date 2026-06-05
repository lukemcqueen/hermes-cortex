---
language: csharp
tags: [csharp, classes, records, structs, init, required]
title: Classes, Records & Structs
description: Modern C# type patterns: positional records, readonly structs, required members with primary constructors, and init-only property setters.
source: pattern
---

```csharp
// Positional record — value-based equality, deconstruction, with-expressions
public record Person(string FirstName, string LastName, int Age);

// Record struct — immutable value type with positional constructor
public readonly record struct Point(double X, double Y);

// Classic class with required members and init-only setters
public class Product
{
    public required Guid Id { get; init; }
    public required string Name { get; set; }
    public decimal Price { get; init; }
    public string? Description { get; set; }

    public override string ToString() => $"{Name} ({Id}) — {Price:C}";
}

// Usage
Person p = new("Jane", "Doe", 30);
Person older = p with { Age = 31 };          // Non-destructive mutation
var (first, last, age) = older;              // Deconstruction

var product = new Product
{
    Id = Guid.NewGuid(),
    Name = "Widget",
    Price = 9.99m
};

```
