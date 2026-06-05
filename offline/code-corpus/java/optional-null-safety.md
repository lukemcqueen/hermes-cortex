---
language: java
tags: [pattern, util]
title: Optional & Null Safety
description: Optional.of/empty/ofNullable, orElse/orElseThrow, ifPresent, map/filter on Optional.
source: pattern
---

```java
import java.util.*;

public class OptionalDemo {
    public static Optional<String> findUserEmail(Long id) {
        Map<Long, String> db = Map.of(1L, "alice@example.com");
        return Optional.ofNullable(db.get(id));
    }

    public static void main(String[] args) {
        // Creation
        Optional<String> present = Optional.of("hello");
        Optional<String> absent = Optional.empty();
        Optional<String> nullable = Optional.ofNullable(null);

        // Retrieval with defaults
        String val1 = absent.orElse("default");
        String val2 = absent.orElseGet(() -> "computed default");
        // String val3 = absent.orElseThrow();          // Java 10+
        // String val4 = absent.orElseThrow(() -> new NoSuchElementException("missing"));

        System.out.println(val1);  // default

        // ifPresent
        present.ifPresent(s -> System.out.println("Found: " + s));  // Found: hello

        // map / filter
        Optional<Integer> length = present.map(String::length);
        System.out.println(length.orElse(0));  // 5

        Optional<String> filtered = present.filter(s -> s.startsWith("h"));
        System.out.println(filtered.isPresent());  // true

        // Chaining with flatMap
        Optional<String> email = findUserEmail(1L)
                .filter(e -> e.contains("@"))
                .map(String::toLowerCase);
        System.out.println(email.orElse("no email"));  // alice@example.com

        // Avoid: Optional.ofNullable(getValue()) for method return types
        // Avoid: Optional as method parameter — overload instead
        // Avoid: Optional in fields / serialization
    }
}

```
