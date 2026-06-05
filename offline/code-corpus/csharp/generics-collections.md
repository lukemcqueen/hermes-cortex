---
language: csharp
tags: [csharp, generics, collections, list, dictionary, constraints]
title: Generics & Collections
description: Generic methods and types, collection initialisers, Dictionary/HashSet, generic constraints (where), covariance/contravariance with in/out.
source: pattern
---

```csharp
// ── Generic repository interface ───────────────────────────────────────
public interface IRepository<T> where T : class, IEntity
{
    T? GetById(int id);
    IReadOnlyList<T> GetAll();
    void Add(T entity);
}

// ── Concrete implementation ────────────────────────────────────────────
public class InMemoryRepository<T> : IRepository<T> where T : class, IEntity
{
    private readonly Dictionary<int, T> _store = new();

    public T? GetById(int id) => _store.GetValueOrDefault(id);
    public IReadOnlyList<T> GetAll() => _store.Values.ToList();
    public void Add(T entity) => _store[entity.Id] = entity;
}

// ── Covariance (out) and Contravariance (in) ───────────────────────────
public interface IProducer<out T> { T Produce(); }
public interface IConsumer<in T> { void Consume(T item); }

// ── Collection initialisers ────────────────────────────────────────────
var lookup = new Dictionary<string, HashSet<int>>
{
    ["even"] = { 2, 4, 6, 8, 10 },
    ["odd"]  = { 1, 3, 5, 7, 9 }
};

// ── Generic constraints ────────────────────────────────────────────────
public static T Max<T>(T a, T b) where T : IComparable<T> =>
    a.CompareTo(b) > 0 ? a : b;

// ── Usage ──────────────────────────────────────────────────────────────
public interface IEntity { int Id { get; } }
public record Order(int Id, decimal Amount) : IEntity;

var repo = new InMemoryRepository<Order>();
repo.Add(new Order(1, 49.99m));

```
