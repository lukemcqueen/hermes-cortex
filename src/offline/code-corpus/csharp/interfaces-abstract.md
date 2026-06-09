---
language: csharp
tags: [csharp, interfaces, abstract, default-implementation, explicit-implementation]
title: Interfaces & Abstract Classes
description: Interface contracts, default interface methods (C# 8+), explicit implementation for disambiguation, and abstract class hierarchies.
source: pattern
---

```csharp
// Interface with default method implementation
public interface ILogger
{
    void Log(string message);
    void LogWarning(string message) => Log($"[WARN] {message}");   // default
    void LogError(string message) => Log($"[ERR]  {message}");     // default
}

// Explicit interface implementation to avoid ambiguity
public class ConsoleLogger : ILogger
{
    void ILogger.Log(string message) =>
        Console.WriteLine($"{DateTime.UtcNow:O} {message}");

    // Provide a public surface that delegates to the explicit impl
    public void LogInfo(string msg) => ((ILogger)this).Log(msg);
}

// Abstract base class
public abstract class Shape
{
    public abstract double Area { get; }
    public virtual string Describe() => $"Shape with area {Area:F2}";
}

public sealed class Circle : Shape
{
    public double Radius { get; }
    public Circle(double radius) => Radius = radius;
    public override double Area => Math.PI * Radius * Radius;
}

```
