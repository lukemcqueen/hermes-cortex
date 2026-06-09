---
language: java
tags: [pattern, util]
title: Records, Text Blocks & Switch
description: Text block """ syntax, record classes, enhanced switch with yield, and pattern matching.
source: pattern
---

```java
// Record
public record Product(String sku, String name, double price) {}

public class RecordsTextBlocksDemo {
    public static void main(String[] args) {
        // Text block (Java 13+)
        String html = """
                <html>
                    <body>
                        <h1>Hello, %s!</h1>
                        <p>Price: $%.2f</p>
                    </body>
                </html>
                """.formatted("Widget A", 19.99);
        System.out.println(html);

        // JSON text block
        String json = """
                {
                    "sku": "WID-001",
                    "name": "Widget A",
                    "price": 19.99
                }
                """;
        System.out.println(json.stripIndent());

        // Record usage
        Product p = new Product("WID-001", "Widget A", 19.99);
        System.out.println(p.name() + " — $" + p.price());

        // Switch with yield (Java 14+)
        String dayName = "WEDNESDAY";
        int dayNumber = switch (dayName) {
            case "MONDAY"    -> 1;
            case "TUESDAY"   -> 2;
            case "WEDNESDAY" -> 3;
            case "THURSDAY"  -> 4;
            case "FRIDAY"    -> 5;
            case "SATURDAY"  -> 6;
            case "SUNDAY"    -> 7;
            default          -> {
                System.err.println("Invalid day: " + dayName);
                yield -1;
            }
        };
        System.out.println(dayName + " is day " + dayNumber);

        // Pattern matching for instanceof (Java 16+)
        Object obj = p;
        if (obj instanceof Product product) {
            System.out.println("Matched product: " + product.name());
        }
    }
}

```
