---
language: java
tags: [pattern, util]
title: Streams & Lambdas
description: Stream API with map/filter/reduce/collect/groupingBy/toList, lambda syntax, and method references.
source: pattern
---

```java
import java.util.*;
import java.util.stream.*;

public class StreamDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Alice", "Bob", "Charlie", "Diana", "Alex");

        // Filter + map + collect
        List<String> upperLong = names.stream()
                .filter(n -> n.length() > 3)
                .map(String::toUpperCase)
                .collect(Collectors.toList());
        System.out.println(upperLong);  // [ALICE, CHARLIE, DIANA]

        // groupingBy
        Map<Integer, List<String>> byLength = names.stream()
                .collect(Collectors.groupingBy(String::length));
        System.out.println(byLength);   // {3=[Bob, Alex], 5=[Alice, Diana], 7=[Charlie]}

        // reduce
        int sum = Stream.of(1, 2, 3, 4, 5)
                .reduce(0, Integer::sum);
        System.out.println(sum);        // 15

        // toList (Java 16+)
        var doubled = Stream.of(2, 4, 6)
                .map(n -> n * 2)
                .toList();
        System.out.println(doubled);    // [4, 8, 12]

        // Method reference ::
        names.forEach(System.out::println);
    }
}

```
