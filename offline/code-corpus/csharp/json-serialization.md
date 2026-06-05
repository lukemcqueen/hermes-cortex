---
language: csharp
tags: [csharp, json, serialization, System.Text.Json, source-generators]
title: JSON & Serialization
description: System.Text.Json: serialise/deserialise, JsonDocument for dynamic access, custom JsonConverter<T>, and source generators for AOT/trimming-safe code.
source: pattern
---

```csharp
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

```
