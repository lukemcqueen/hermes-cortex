---
language: java
tags: [pattern, util]
title: Generics & Collections
description: Generic classes/methods, wildcards (? extends T), and typed collections with List/Set/Map.
source: pattern
---

```java
import java.util.*;

// Generic class
public class Box<T> {
    private T value;

    public Box(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    // Generic method
    public static <U> Box<U> of(U item) {
        return new Box<>(item);
    }

    // Wildcard — accepts any Number subtype
    public static double sumOf(Box<? extends Number> box) {
        return box.get().doubleValue();
    }

    public static void main(String[] args) {
        Box<String> stringBox = new Box<>("Hello");
        System.out.println(stringBox.get());

        Box<Integer> intBox = Box.of(42);
        System.out.println(sumOf(intBox));      // 42.0

        Box<Double> dblBox = Box.of(3.14);
        System.out.println(sumOf(dblBox));      // 3.14

        // Typed collections
        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
        Set<String> nameSet = new HashSet<>(Set.of("Alice", "Bob"));
        Map<String, Integer> scores = new HashMap<>(Map.of("Alice", 95, "Bob", 87));

        // Collections utility
        Collections.sort(numbers);
        Collections.reverse(numbers);
        System.out.println(numbers);            // [3, 2, 1]
    }
}

```
