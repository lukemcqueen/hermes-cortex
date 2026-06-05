---
language: csharp
tags: [csharp, logging, ILogger, serilog, structured-logging, log-levels]
title: Logging
description: ILogger<T> structured logging, log levels, Serilog sink configuration, scoped logging, and best practices for semantic output.
source: pattern
---

```csharp
// ── Built-in ILogger<T> ────────────────────────────────────────────────
public class OrderProcessor
{
    private readonly ILogger<OrderProcessor> _logger;

    public OrderProcessor(ILogger<OrderProcessor> logger) => _logger = logger;

    public async Task ProcessAsync(Order order)
    {
        // Structured logging — never string interpolation!
        _logger.LogInformation("Processing order {OrderId} for {Customer}",
            order.Id, order.CustomerName);

        try
        {
            // ... work ...
            _logger.LogDebug("Payment {PaymentId} settled", order.PaymentId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to process order {OrderId}", order.Id);
            throw;
        }
    }

    // Scoped logging — all messages within the scope carry these properties
    public async Task HandleRequestAsync(HttpContext context)
    {
        using var _ = _logger.BeginScope(new Dictionary<string, object>
        {
            ["RequestId"] = context.TraceIdentifier,
            ["Path"] = context.Request.Path
        });
        // ... all logs here include RequestId and Path
    }
}

// ── Serilog configuration (Program.cs) ─────────────────────────────────
// using Serilog;
//
// Log.Logger = new LoggerConfiguration()
//     .MinimumLevel.Information()
//     .MinimumLevel.Override("Microsoft", LogEventLevel.Warning)
//     .WriteTo.Console(outputTemplate:
//         "[{Timestamp:HH:mm:ss} {Level:u3}] {Message:lj}{NewLine}{Exception}")
//     .WriteTo.File("logs/app-.log", rollingInterval: RollingInterval.Day)
//     .Enrich.FromLogContext()
//     .CreateLogger();
//
// builder.Host.UseSerilog();

// Log levels from lowest to highest:
//   Trace → Debug → Information → Warning → Error → Fatal

```
