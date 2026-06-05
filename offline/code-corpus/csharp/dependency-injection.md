---
language: csharp
tags: [csharp, di, dependency-injection, IServiceCollection, options-pattern]
title: Dependency Injection
description: Registering services with IServiceCollection, constructor injection, scoped/transient/singleton lifetimes, and the options pattern with IOptions<T>.
source: pattern
---

```csharp
// ── Registration (typically in Program.cs or a Startup-like class) ─────
var builder = WebApplication.CreateBuilder(args);

builder.Services.AddSingleton<ITimeProvider, SystemClock>();
builder.Services.AddScoped<IOrderRepository, OrderRepository>();
builder.Services.AddTransient<IEmailService, SmtpEmailService>();

// Options pattern — binds section to strongly-typed class
builder.Services.Configure<FeatureToggles>(
    builder.Configuration.GetSection("FeatureToggles"));

builder.Services.AddHttpClient<IPaymentGateway, StripeGateway>(client =>
{
    client.BaseAddress = new Uri("https://api.stripe.com/v1/");
});

// ── Consumption via constructor injection ─────────────────────────────
public class OrderService
{
    private readonly IOrderRepository _repo;
    private readonly IEmailService _email;
    private readonly IOptions<FeatureToggles> _features;

    public OrderService(
        IOrderRepository repo,
        IEmailService email,
        IOptions<FeatureToggles> features)
    {
        _repo = repo;
        _email = email;
        _features = features;
    }

    public async Task PlaceOrderAsync(Order order)
    {
        await _repo.SaveAsync(order);
        if (_features.Value.SendConfirmationEmails)
            await _email.SendReceiptAsync(order);
    }
}

```
