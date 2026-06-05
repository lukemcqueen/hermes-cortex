---
language: csharp
tags: [csharp, file-io, stream, async-io, Path]
title: File I/O
description: Synchronous and asynchronous file reading/writing, StreamReader/StreamWriter, FileStream, and safe path construction with Path.Combine.
source: pattern
---

```csharp
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

```
