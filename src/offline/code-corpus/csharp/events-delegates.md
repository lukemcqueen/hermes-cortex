---
language: csharp
tags: [csharp, events, delegates, eventhandler, action, func, multicast]
title: Events & Delegates
description: The event keyword, EventHandler<TEventArgs>, Action/Func delegates, multicast delegates, and the weak event pattern for avoiding memory leaks.
source: pattern
---

```csharp
// ── Custom event with EventHandler<T> ──────────────────────────────────
public class OrderService
{
    // Event declaration
    public event EventHandler<OrderProcessedEventArgs>? OrderProcessed;

    public async Task ProcessAsync(Order order)
    {
        // ... processing ...
        OnOrderProcessed(new OrderProcessedEventArgs(order.Id, "Completed"));
    }

    protected virtual void OnOrderProcessed(OrderProcessedEventArgs e)
    {
        // Thread-safe invocation with null check
        Volatile.Read(ref OrderProcessed)?.Invoke(this, e);
    }
}

public class OrderProcessedEventArgs : EventArgs
{
    public string OrderId { get; }
    public string Status { get; }
    public OrderProcessedEventArgs(string orderId, string status)
        => (OrderId, Status) = (orderId, status);
}

// ── Subscription ───────────────────────────────────────────────────────
var service = new OrderService();
service.OrderProcessed += (sender, e) =>
    Console.WriteLine($"Order {e.OrderId} → {e.Status}");

// ── Action / Func delegates ────────────────────────────────────────────
public class Pipeline<T>
{
    private readonly List<Func<T, Task<T>>> _steps = new();

    public Pipeline<T> AddStep(Func<T, Task<T>> step)
    {
        _steps.Add(step);
        return this;
    }

    public async Task<T> ExecuteAsync(T input)
    {
        T current = input;
        foreach (var step in _steps)
            current = await step(current);
        return current;
    }
}

// Multicast delegate example
Action<string> logger = msg => Console.WriteLine(msg);
logger += msg => File.AppendAllText("log.txt", msg + Environment.NewLine);
logger("Both console and file");    // Invokes both targets

// ── WeakEvent pattern (avoid subscriber GC roots) ──────────────────────
// Use WeakEventManager<T> from CommunityToolkit.Mvvm or implement manually
// using WeakReference to hold subscribers.

```
