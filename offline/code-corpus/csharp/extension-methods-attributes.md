---
language: csharp
tags: [csharp, extension-methods, attributes, caller-info, custom-attributes]
title: Extension Methods & Attributes
description: Static class with the this parameter, [Obsolete], [CallerMemberName], custom attribute creation, and reflection-based filtering.
source: pattern
---

```csharp
// ── Extension methods ──────────────────────────────────────────────────
public static class StringExtensions
{
    public static bool IsNullOrWhiteSpace(this string? value) =>
        string.IsNullOrWhiteSpace(value);

    public static string Truncate(this string value, int maxLength, string suffix = "...") =>
        value.Length <= maxLength ? value
            : value[..(maxLength - suffix.Length)] + suffix;
}

// ── Usage ──────────────────────────────────────────────────────────────
string? maybeNull = null;
bool blank = maybeNull.IsNullOrWhiteSpace();         // true
string trimmed = "Hello, World!".Truncate(8);        // "Hello..."

// ── Attributes ─────────────────────────────────────────────────────────
[Obsolete("Use NewMethod instead", error: false)]
public static string OldMethod() => "deprecated";

public class Logger
{
    public void LogMessage(string message,
        [CallerMemberName] string member = "",
        [CallerFilePath] string file = "",
        [CallerLineNumber] int line = 0)
    {
        Console.WriteLine($"[{member} @ {file}:{line}] {message}");
    }
}

// ── Custom attribute ───────────────────────────────────────────────────
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method, AllowMultiple = false)]
public class RateLimitAttribute : Attribute
{
    public int MaxRequests { get; }
    public int WindowSeconds { get; }
    public RateLimitAttribute(int maxRequests, int windowSeconds = 60)
    {
        MaxRequests = maxRequests;
        WindowSeconds = windowSeconds;
    }
}

[RateLimit(100, WindowSeconds = 10)]
public class ApiController { /* ... */ }

// ── Reading attributes via reflection ──────────────────────────────────
var attr = typeof(ApiController).GetCustomAttribute<RateLimitAttribute>();
if (attr is not null)
    Console.WriteLine($"Rate limit: {attr.MaxRequests} req/{attr.WindowSeconds}s");

```
