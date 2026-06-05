---
language: csharp
tags: [csharp, exceptions, try-catch, when-filter, custom-exception]
title: Exception Handling
description: Try-catch-finally, custom exceptions, exception filters (when), async exception handling, and AggregateException for task faults.
source: pattern
---

```csharp
// ── Custom exception ───────────────────────────────────────────────────
public class OrderProcessingException : Exception
{
    public string OrderId { get; }
    public OrderProcessingException(string orderId, string message, Exception? inner = null)
        : base(message, inner) => OrderId = orderId;
}

// ── Exception filters & structured handling ───────────────────────────
public async Task ProcessOrderAsync(string orderId)
{
    try
    {
        // ... processing logic ...
    }
    catch (OrderProcessingException ex) when (ex.OrderId == orderId)
    {
        // Only catch if the order ID matches
        await LogErrorAsync($"Order {orderId} failed: {ex.Message}");
        throw;          // re-throw if not recoverable
    }
    catch (HttpRequestException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
    {
        // Swallow 404 — resource already deleted
        Console.WriteLine($"Resource not found (expected): {ex.Message}");
    }
    catch (Exception ex) when (LogAndReturnFalse(ex))
    {
        // Filter method must return false — this block is never entered,
        // but the side-effect (logging) always runs.
    }
    finally
    {
        await CleanupAsync(orderId);
    }
}

static bool LogAndReturnFalse(Exception ex)
{
    Console.Error.WriteLine($"Unhandled: {ex}");
    return false;   // prevents catch block from executing
}

// ── AggregateException (from Task.WhenAll etc.) ────────────────────────
try
{
    await Task.WhenAll(Crash1Async(), Crash2Async());
}
catch (AggregateException ae)
{
    foreach (var inner in ae.InnerExceptions)
        Console.Error.WriteLine($"Task faulted: {inner.Message}");
}
// Or use .Unwrap() / await handles flattened exceptions automatically

```
