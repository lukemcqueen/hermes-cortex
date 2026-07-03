---
language: csharp
tags: [csharp, async, await, task, cancellation, IAsyncEnumerable]
title: Async/Await & Tasks
description: Async methods, Task.Run for CPU-bound work, Task.WhenAll/WhenAny for concurrency, CancellationToken support, and IAsyncEnumerable for async streams.
source: pattern
---

```csharp
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

```
