---
language: java
tags: [pattern, util]
title: Classes, Records & Sealed Classes
description: Modern Java classes, records for data carriers, and sealed hierarchies with permits.
source: pattern
---

```java
// Record — concise data carrier (Java 16+)
public record Point(int x, int y) {}

// Sealed hierarchy (Java 17+)
public sealed interface Shape permits Circle, Rectangle {}

public record Circle(double radius) implements Shape {}
public record Rectangle(double width, double height) implements Shape {}

// Static nested class with access modifiers
public class Outer {
    private static int counter = 0;

    public static class Nested {
        public void increment() {
            counter++;
        }
    }

    public static void main(String[] args) {
        Point p = new Point(3, 4);
        System.out.println("x = " + p.x());  // accessor, not getX()

        Shape s = new Circle(5.0);
        if (s instanceof Circle c) {
            System.out.println("Area: " + Math.PI * c.radius() * c.radius());
        }

        Nested n = new Nested();
        n.increment();
        n.increment();
        System.out.println("Counter: " + counter);
    }
}

```
