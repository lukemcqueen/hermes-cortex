---
language: csharp
tags: [csharp, entity-framework, ef-core, dbcontext, migrations, linq]
title: Entity Framework Core
description: DbContext with DbSet, relationship configuration, async LINQ queries, eager loading (Include/ThenInclude), migrations, and SaveChangesAsync.
source: pattern
---

```csharp
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

```
