---
language: csharp
tags: [csharp, aspnetcore, webapi, controller, middleware, ef-core]
title: ASP.NET Core Web API
description: Minimal API and controller-based endpoints, Entity Framework integration, custom middleware, and structured response with IActionResult.
source: pattern
---

```csharp
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

```
