---
language: csharp
tags: [csharp, configuration, options-pattern, IConfiguration, appsettings]
title: Configuration & Options
description: IConfiguration binding, strongly-typed options with IOptions/IOptionsSnapshot, environment variables, User Secrets, and named options.
source: pattern
---

```csharp
// ── appsettings.json ───────────────────────────────────────────────────
// {
//   "Database": {
//     "ConnectionString": "Server=.;Database=MyDb;Trusted_Connection=True;",
//     "TimeoutSeconds": 30
//   },
//   "Email": {
//     "SmtpHost": "smtp.example.com",
//     "Port": 587,
//     "UseSsl": true
//   }
// }

// ── Strongly-typed configuration classes ──────────────────────────────
public class DatabaseOptions
{
    public const string SectionName = "Database";
    public string ConnectionString { get; set; } = string.Empty;
    public int TimeoutSeconds { get; set; } = 30;
}

public class EmailOptions
{
    public const string SectionName = "Email";
    public string SmtpHost { get; set; } = string.Empty;
    public int Port { get; set; } = 587;
    public bool UseSsl { get; set; } = true;
}

// ── Registration ───────────────────────────────────────────────────────
var builder = WebApplication.CreateBuilder(args);

builder.Services.Configure<DatabaseOptions>(
    builder.Configuration.GetSection(DatabaseOptions.SectionName));

builder.Services.Configure<EmailOptions>(
    builder.Configuration.GetSection(EmailOptions.SectionName));

// ── Consumption ────────────────────────────────────────────────────────
public class EmailSender
{
    private readonly EmailOptions _options;

    // IOptions<T> — singleton, reads once at startup
    // IOptionsSnapshot<T> — scoped, re-reads per request
    // IOptionsMonitor<T> — singleton, updated on config change
    public EmailSender(IOptions<EmailOptions> options)
    {
        _options = options.Value;
    }

    public SmtpClient CreateClient() => new(_options.SmtpHost, _options.Port)
    {
        EnableSsl = _options.UseSsl
    };
}

// ── Environment variables override (dot-separated) ─────────────────────
// $"Email__SmtpHost" or "Email:SmtpHost" (platform-dependent)
// Also supported: User Secrets during development via `dotnet user-secrets set`

```
