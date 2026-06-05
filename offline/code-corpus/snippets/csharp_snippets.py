"""
C# Snippet Module
=================
18 C# code snippets covering modern .NET patterns (C# 10/12, .NET 6+).
Each entry is a 7-tuple: (rel_path, language, tags, title, description, source, code).
"""

SNIPPETS = [
    # ── 1. Classes, Records & Structs ──────────────────────────────────────────────
    (
        "csharp/classes-records-structs.md",
        "csharp",
        ["csharp", "classes", "records", "structs", "init", "required"],
        "Classes, Records & Structs",
        "Modern C# type patterns: positional records, readonly structs, required "
        "members with primary constructors, and init-only property setters.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 2. Interfaces & Abstract Classes ──────────────────────────────────────────
    (
        "csharp/interfaces-abstract.md",
        "csharp",
        ["csharp", "interfaces", "abstract", "default-implementation", "explicit-implementation"],
        "Interfaces & Abstract Classes",
        "Interface contracts, default interface methods (C# 8+), explicit "
        "implementation for disambiguation, and abstract class hierarchies.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 3. LINQ & Lambda ───────────────────────────────────────────────────────────
    (
        "csharp/linq-lambda.md",
        "csharp",
        ["csharp", "linq", "lambda", "deferred-execution", "query-syntax"],
        "LINQ & Lambda Expressions",
        "Method-syntax and query-syntax LINQ, deferred execution with IEnumerable, "
        "GroupBy, Aggregate, and Any/All checks.",
        "pattern",
        r'''```csharp
var numbers = Enumerable.Range(1, 100);

// Method syntax — fluent
var result = numbers
    .Where(n => n % 3 == 0)
    .OrderByDescending(n => n)
    .Select(n => new { Original = n, Squared = n * n })
    .Take(5)
    .ToList();

// Query syntax (expression tree equivalent)
var query = from n in numbers
            where n % 3 == 0
            orderby n descending
            select new { Original = n, Squared = n * n };

// GroupBy
var grouped = numbers.GroupBy(n => n % 2 == 0 ? "Even" : "Odd");

// Aggregate (fold)
int sum = numbers.Aggregate(0, (acc, n) => acc + n);

// Any / All
bool hasPrimes = numbers.Any(n => n is 2 or 3 or 5 or 7);
bool allPositive = numbers.All(n => n > 0);

// Deferred execution (IEnumerable is lazy; ToList/ToArray materialises)
IEnumerable<int> deferred = numbers.Where(n => n > 50);   // not executed yet
var materialised = deferred.ToList();                     // executed now
```''',
    ),

    # ── 4. Async/Await & Tasks ─────────────────────────────────────────────────────
    (
        "csharp/async-await-tasks.md",
        "csharp",
        ["csharp", "async", "await", "task", "cancellation", "IAsyncEnumerable"],
        "Async/Await & Tasks",
        "Async methods, Task.Run for CPU-bound work, Task.WhenAll/WhenAny for "
        "concurrency, CancellationToken support, and IAsyncEnumerable for async streams.",
        "pattern",
        r'''```csharp
public class DataService
{
    private readonly HttpClient _http;

    public DataService(HttpClient http) => _http = http;

    // Standard async method
    public async Task<string> FetchDataAsync(string url, CancellationToken ct = default)
    {
        var response = await _http.GetAsync(url, ct);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(ct);
    }

    // Concurrent fan-out
    public async Task<string[]> FetchAllAsync(IEnumerable<string> urls, CancellationToken ct)
    {
        var tasks = urls.Select(url => FetchDataAsync(url, ct));
        return await Task.WhenAll(tasks);
    }

    // Async stream (C# 8 IAsyncEnumerable)
    public async IAsyncEnumerable<int> GenerateSequenceAsync(
        int start, int count, [EnumeratorCancellation] CancellationToken ct = default)
    {
        for (int i = start; i < start + count; i++)
        {
            ct.ThrowIfCancellationRequested();
            await Task.Delay(100, ct);          // simulate async work
            yield return i;
        }
    }

    // Fire-and-forget with error logging (use carefully)
    public void FireAndForget(Task task) =>
        _ = task.ContinueWith(t =>
            Console.Error.WriteLine($"Background fault: {t.Exception}"),
            TaskContinuationOptions.OnlyOnFaulted);
}
```''',
    ),

    # ── 5. Dependency Injection ────────────────────────────────────────────────────
    (
        "csharp/dependency-injection.md",
        "csharp",
        ["csharp", "di", "dependency-injection", "IServiceCollection", "options-pattern"],
        "Dependency Injection",
        "Registering services with IServiceCollection, constructor injection, "
        "scoped/transient/singleton lifetimes, and the options pattern with IOptions<T>.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 6. File I/O ────────────────────────────────────────────────────────────────
    (
        "csharp/file-io.md",
        "csharp",
        ["csharp", "file-io", "stream", "async-io", "Path"],
        "File I/O",
        "Synchronous and asynchronous file reading/writing, StreamReader/StreamWriter, "
        "FileStream, and safe path construction with Path.Combine.",
        "pattern",
        r'''```csharp
public static class FileHelper
{
    // Simple text read/write
    public static async Task<string> ReadAllTextAsync(string path) =>
        await File.ReadAllTextAsync(path);

    public static async Task WriteAllTextAsync(string path, string content) =>
        await File.WriteAllTextAsync(path, content);

    // Streaming — large files
    public static async IAsyncEnumerable<string> ReadLinesAsync(string path,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        using var reader = new StreamReader(path);
        while (await reader.ReadLineAsync(ct) is { } line)
            yield return line;
    }

    public static async Task AppendLinesAsync(string path, IEnumerable<string> lines,
        CancellationToken ct = default)
    {
        await using var writer = new StreamWriter(path, append: true);
        foreach (var line in lines)
        {
            await writer.WriteLineAsync(line.ToCharArray(), ct);
        }
    }

    // Binary — FileStream with buffer
    public static async Task CopyAsync(string source, string destination,
        CancellationToken ct = default)
    {
        await using var src = new FileStream(source, FileMode.Open, FileAccess.Read,
            FileShare.Read, 65536, useAsync: true);
        await using var dst = new FileStream(destination, FileMode.Create,
            FileAccess.Write, FileShare.None, 65536, useAsync: true);
        await src.CopyToAsync(dst, ct);
    }

    // Safe path construction
    public static string CombineWithCheck(string basePath, string relative) =>
        Path.GetFullPath(Path.Combine(basePath, relative));
}
```''',
    ),

    # ── 7. JSON & Serialization ────────────────────────────────────────────────────
    (
        "csharp/json-serialization.md",
        "csharp",
        ["csharp", "json", "serialization", "System.Text.Json", "source-generators"],
        "JSON & Serialization",
        "System.Text.Json: serialise/deserialise, JsonDocument for dynamic access, "
        "custom JsonConverter<T>, and source generators for AOT/trimming-safe code.",
        "pattern",
        r'''```csharp
using System.Text.Json;
using System.Text.Json.Serialization;

// ── Basic serialisation ────────────────────────────────────────────────
public class WeatherForecast
{
    public DateTime Date { get; set; }
    public int TemperatureC { get; set; }
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Summary { get; set; }
}

var forecast = new WeatherForecast
{
    Date = DateTime.UtcNow,
    TemperatureC = 22,
    Summary = "Mild"
};

string json = JsonSerializer.Serialize(forecast, new JsonSerializerOptions
{
    WriteIndented = true,
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase
});

var deserialised = JsonSerializer.Deserialize<WeatherForecast>(json);

// ── Dynamic / untyped access with JsonDocument ─────────────────────────
using JsonDocument doc = JsonDocument.Parse(json);
int temp = doc.RootElement.GetProperty("temperatureC").GetInt32();

// ── Custom converter ───────────────────────────────────────────────────
public class GuidTruncatedConverter : JsonConverter<Guid>
{
    public override Guid Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions o) =>
        Guid.Parse(reader.GetString()!);

    public override void Write(Utf8JsonWriter writer, Guid value, JsonSerializerOptions o) =>
        writer.WriteStringValue(value.ToString("N")[..8]);
}

// ── Source generator (trim-safe, AOT-friendly) ─────────────────────────
[JsonSerializable(typeof(WeatherForecast))]
[JsonSerializable(typeof(List<WeatherForecast>))]
internal partial class AppJsonContext : JsonSerializerContext { }

// Usage: JsonSerializer.Serialize(forecast, AppJsonContext.Default.WeatherForecast);
```''',
    ),

    # ── 8. ASP.NET Core Web API ────────────────────────────────────────────────────
    (
        "csharp/aspnetcore-webapi.md",
        "csharp",
        ["csharp", "aspnetcore", "webapi", "controller", "middleware", "ef-core"],
        "ASP.NET Core Web API",
        "Minimal API and controller-based endpoints, Entity Framework integration, "
        "custom middleware, and structured response with IActionResult.",
        "pattern",
        r'''```csharp
// ── Program.cs (Minimal API style) ─────────────────────────────────────
var builder = WebApplication.CreateBuilder(args);

builder.Services.AddDbContext<AppDbContext>(o =>
    o.UseSqlServer(builder.Configuration.GetConnectionString("Default")));

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();

// Minimal API endpoints
app.MapGet("/products", async (AppDbContext db) =>
    await db.Products.ToListAsync());

app.MapGet("/products/{id}", async (int id, AppDbContext db) =>
    await db.Products.FindAsync(id) is Product p ? Results.Ok(p) : Results.NotFound());

app.MapPost("/products", async (Product product, AppDbContext db) =>
{
    db.Products.Add(product);
    await db.SaveChangesAsync();
    return Results.Created($"/products/{product.Id}", product);
});

// ── Custom middleware ──────────────────────────────────────────────────
app.Use(async (context, next) =>
{
    var sw = Stopwatch.StartNew();
    await next(context);
    sw.Stop();
    context.Response.Headers["X-Response-Time-Ms"] = sw.ElapsedMilliseconds.ToString();
});

app.Run();

// ── Controller-based alternative ───────────────────────────────────────
[ApiController]
[Route("api/[controller]")]
public class ProductsController : ControllerBase
{
    private readonly AppDbContext _db;
    public ProductsController(AppDbContext db) => _db = db;

    [HttpGet]
    public async Task<ActionResult<List<Product>>> GetAll() =>
        await _db.Products.AsNoTracking().ToListAsync();

    [HttpGet("{id}")]
    public async Task<ActionResult<Product>> GetById(int id) =>
        await _db.Products.FindAsync(id) is Product p ? Ok(p) : NotFound();
}
```''',
    ),

    # ── 9. Generics & Collections ──────────────────────────────────────────────────
    (
        "csharp/generics-collections.md",
        "csharp",
        ["csharp", "generics", "collections", "list", "dictionary", "constraints"],
        "Generics & Collections",
        "Generic methods and types, collection initialisers, Dictionary/HashSet, "
        "generic constraints (where), covariance/contravariance with in/out.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 10. Null Safety & Pattern Matching ─────────────────────────────────────────
    (
        "csharp/null-safety-pattern-matching.md",
        "csharp",
        ["csharp", "null-safety", "nullable", "pattern-matching", "switch-expression"],
        "Null Safety & Pattern Matching",
        "Nullable reference types, null-forgiving operator, null-conditional ?., "
        "switch expressions, property patterns, list patterns, and relational patterns.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 11. Exception Handling ──────────────────────────────────────────────────────
    (
        "csharp/exception-handling.md",
        "csharp",
        ["csharp", "exceptions", "try-catch", "when-filter", "custom-exception"],
        "Exception Handling",
        "Try-catch-finally, custom exceptions, exception filters (when), "
        "async exception handling, and AggregateException for task faults.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 12. Entity Framework Core ───────────────────────────────────────────────────
    (
        "csharp/entity-framework-core.md",
        "csharp",
        ["csharp", "entity-framework", "ef-core", "dbcontext", "migrations", "linq"],
        "Entity Framework Core",
        "DbContext with DbSet, relationship configuration, async LINQ queries, "
        "eager loading (Include/ThenInclude), migrations, and SaveChangesAsync.",
        "pattern",
        r'''```csharp
using Microsoft.EntityFrameworkCore;

// ── DbContext ──────────────────────────────────────────────────────────
public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<Blog> Blogs => Set<Blog>();
    public DbSet<Post> Posts => Set<Post>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Blog>(b =>
        {
            b.HasKey(x => x.Id);
            b.Property(x => x.Name).HasMaxLength(200).IsRequired();
            b.HasMany(x => x.Posts)
             .WithOne(x => x.Blog)
             .HasForeignKey(x => x.BlogId)
             .OnDelete(DeleteBehavior.Cascade);
        });
    }
}

// ── Entities ───────────────────────────────────────────────────────────
public class Blog
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public List<Post> Posts { get; set; } = new();
}

public class Post
{
    public int Id { get; set; }
    public string Title { get; set; } = string.Empty;
    public string? Content { get; set; }
    public int BlogId { get; set; }
    public Blog Blog { get; set; } = null!;
}

// ── Queries ────────────────────────────────────────────────────────────
public class BlogService
{
    private readonly AppDbContext _db;
    public BlogService(AppDbContext db) => _db = db;

    public async Task<List<Blog>> GetBlogsWithRecentPostsAsync(int daysBack)
    {
        var cutoff = DateTime.UtcNow.AddDays(-daysBack);
        return await _db.Blogs
            .Include(b => b.Posts.Where(p => p.Id > 0))  // EF Core 6+ filtered include
            .ThenInclude(p => p.Blog)                     // back-reference
            .AsNoTracking()
            .OrderBy(b => b.Name)
            .ToListAsync();
    }

    public async Task<int> ArchiveOldPostsAsync(int daysBack)
    {
        var cutoff = DateTime.UtcNow.AddDays(-daysBack);
        return await _db.Posts
            .Where(p => p.Id < 0)                         // condition placeholder
            .ExecuteDeleteAsync();                        // EF Core 7+ bulk delete
    }
}
```''',
    ),

    # ── 13. Configuration & Options ─────────────────────────────────────────────────
    (
        "csharp/configuration-options.md",
        "csharp",
        ["csharp", "configuration", "options-pattern", "IConfiguration", "appsettings"],
        "Configuration & Options",
        "IConfiguration binding, strongly-typed options with IOptions/IOptionsSnapshot, "
        "environment variables, User Secrets, and named options.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 14. Logging ────────────────────────────────────────────────────────────────
    (
        "csharp/logging.md",
        "csharp",
        ["csharp", "logging", "ILogger", "serilog", "structured-logging", "log-levels"],
        "Logging",
        "ILogger<T> structured logging, log levels, Serilog sink configuration, "
        "scoped logging, and best practices for semantic output.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 15. Extension Methods & Attributes ─────────────────────────────────────────
    (
        "csharp/extension-methods-attributes.md",
        "csharp",
        ["csharp", "extension-methods", "attributes", "caller-info", "custom-attributes"],
        "Extension Methods & Attributes",
        "Static class with the this parameter, [Obsolete], [CallerMemberName], "
        "custom attribute creation, and reflection-based filtering.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 16. Events & Delegates ─────────────────────────────────────────────────────
    (
        "csharp/events-delegates.md",
        "csharp",
        ["csharp", "events", "delegates", "eventhandler", "action", "func", "multicast"],
        "Events & Delegates",
        "The event keyword, EventHandler<TEventArgs>, Action/Func delegates, "
        "multicast delegates, and the weak event pattern for avoiding memory leaks.",
        "pattern",
        r'''```csharp
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
```''',
    ),

    # ── 17. Unsafe & Interop ───────────────────────────────────────────────────────
    (
        "csharp/unsafe-interop.md",
        "csharp",
        ["csharp", "unsafe", "interop", "pointers", "pinvoke", "span", "marshal"],
        "Unsafe Code & Interop",
        "Unsafe blocks with pointers, fixed-size buffers, P/Invoke declarations, "
        "Marshal class for unmanaged memory, and Span<T> for safe stack/memory access.",
        "pattern",
        r'''```csharp
using System.Runtime.InteropServices;

// ── P/Invoke — calling Win32 API ───────────────────────────────────────
public static class NativeMethods
{
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern nint GetModuleHandle(string? lpModuleName);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int MessageBox(nint hWnd, string text, string caption, uint type);
}

// ── Unsafe block with pointers ─────────────────────────────────────────
public static unsafe class FastBuffer
{
    public static void ZeroFill(Span<byte> buffer)
    {
        fixed (byte* ptr = buffer)
        {
            for (int i = 0; i < buffer.Length; i++)
                ptr[i] = 0;
        }
    }

    // Stackalloc + pointer arithmetic
    public static Span<int> GenerateSquares(int count)
    {
        int* arr = stackalloc int[count];
        for (int i = 0; i < count; i++)
            arr[i] = i * i;
        return new Span<int>(arr, count);
    }
}

// ── Marshal — converting unmanaged data ────────────────────────────────
public static class UnmanagedHelper
{
    public static nint AllocateAndCopy(byte[] data)
    {
        nint ptr = Marshal.AllocHGlobal(data.Length);
        Marshal.Copy(data, 0, ptr, data.Length);
        return ptr;
    }

    public static byte[] ReadAndFree(nint ptr, int length)
    {
        byte[] data = new byte[length];
        Marshal.Copy(ptr, data, 0, length);
        Marshal.FreeHGlobal(ptr);
        return data;
    }

    // Struct to byte[] and back
    public static byte[] StructToBytes<T>(T value) where T : struct
    {
        byte[] buffer = new byte[Marshal.SizeOf<T>()];
        Marshal.StructureToPtr(value, Marshal.UnsafeAddrOfPinnedArrayElement(buffer, 0), false);
        return buffer;
    }
}

// ── Span<T> — safe, stack-allocated memory region ──────────────────────
Span<int> stackSpan = stackalloc int[256];
Span<byte> managedSpan = new byte[1024];
ReadOnlySpan<char> slice = "Hello, World!".AsSpan()[7..12]; // "World"
```''',
    ),

    # ── 18. Unit Testing ────────────────────────────────────────────────────────────
    (
        "csharp/unit-testing.md",
        "csharp",
        ["csharp", "testing", "xunit", "moq", "fluentassertions", "nunit"],
        "Unit Testing (xUnit / NUnit)",
        "xUnit [Fact] and [Theory] tests, Moq for mocking dependencies, "
        "FluentAssertions for readable assertions, and NUnit equivalent attributes.",
        "pattern",
        r'''```csharp
using Xunit;
using Moq;
using FluentAssertions;
using static FluentAssertions.FluentActions;

// ── System under test ──────────────────────────────────────────────────
public interface IPriceService { decimal GetDiscount(string customerId); }
public class OrderCalculator
{
    private readonly IPriceService _prices;
    public OrderCalculator(IPriceService prices) => _prices = prices;

    public decimal CalculateTotal(Order order, string customerId)
    {
        var discount = _prices.GetDiscount(customerId);
        return order.Items.Sum(i => i.Price * i.Quantity) * (1 - discount);
    }
}

public record OrderItem(string Sku, decimal Price, int Quantity);
public record Order(List<OrderItem> Items);

// ── xUnit tests ────────────────────────────────────────────────────────
public class OrderCalculatorTests
{
    [Fact]
    public void CalculateTotal_WithDiscount_ReturnsDiscountedSum()
    {
        // Arrange
        var mockPrice = new Mock<IPriceService>();
        mockPrice.Setup(p => p.GetDiscount("vip")).Returns(0.20m);

        var calculator = new OrderCalculator(mockPrice.Object);
        var order = new Order(new List<OrderItem>
        {
            new("ABC", 100m, 2),
            new("DEF", 50m,  1)
        });

        // Act
        var total = calculator.CalculateTotal(order, "vip");

        // Assert (FluentAssertions)
        total.Should().Be(200m);    // (200 + 50) * 0.80
    }

    [Theory]
    [InlineData("standard", 0.00, 250.00)]
    [InlineData("vip",      0.20, 200.00)]
    [InlineData("employee", 0.35, 162.50)]
    public void CalculateTotal_MultipleDiscountLevels_ReturnsExpected(
        string customerId, decimal discount, decimal expected)
    {
        var mockPrice = new Mock<IPriceService>();
        mockPrice.Setup(p => p.GetDiscount(customerId)).Returns(discount);

        var calculator = new OrderCalculator(mockPrice.Object);
        var order = new Order(new List<OrderItem> { new("SKU", 100m, 2), new("SKU2", 50m, 1) });

        var total = calculator.CalculateTotal(order, customerId);
        total.Should().BeApproximately(expected, 0.001m);
    }

    [Fact]
    public void CalculateTotal_NoItems_ReturnsZero()
    {
        var mockPrice = new Mock<IPriceService>();
        var calculator = new OrderCalculator(mockPrice.Object);
        var empty = new Order(new List<OrderItem>());

        var total = calculator.CalculateTotal(empty, "test");

        total.Should().Be(0m);
    }
}

/* ── NUnit equivalent (for reference) ──────────────────────────────────
[TestFixture]
public class OrderCalculatorNUnitTests
{
    private Mock<IPriceService> _mockPrice = null!;
    private OrderCalculator _calculator = null!;

    [SetUp]
    public void Setup()
    {
        _mockPrice = new Mock<IPriceService>();
        _calculator = new OrderCalculator(_mockPrice.Object);
    }

    [Test]
    public void CalculateTotal_WithDiscount_ReturnsDiscountedSum()
    {
        _mockPrice.Setup(p => p.GetDiscount("vip")).Returns(0.20m);
        var order = new Order(new List<OrderItem> { new("ABC", 100m, 2) });

        var total = _calculator.CalculateTotal(order, "vip");

        Assert.That(total, Is.EqualTo(160m).Within(0.001));
    }
}
*/
```''',
    ),
]
