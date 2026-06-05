---
language: java
tags: [pattern, concurrency]
title: CompletableFuture
description: supplyAsync, thenApply/thenCompose, allOf, exceptionally, join, and custom thread pool.
source: pattern
---

```java
import java.util.concurrent.*;
import java.util.stream.*;

public class CompletableFutureDemo {
    private static final ExecutorService CUSTOM_POOL =
            Executors.newFixedThreadPool(4);

    static CompletableFuture<String> fetchUser(Long id) {
        return CompletableFuture.supplyAsync(() -> {
            simulateDelay(200);
            return "User-" + id;
        }, CUSTOM_POOL);
    }

    static CompletableFuture<String> fetchOrders(String user) {
        return CompletableFuture.supplyAsync(() -> {
            simulateDelay(150);
            return user + " has 3 orders";
        }, CUSTOM_POOL);
    }

    static void simulateDelay(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) {
        // Chaining: thenApply
        CompletableFuture.supplyAsync(() -> 5, CUSTOM_POOL)
                .thenApply(n -> n * 2)
                .thenApply(n -> "Result: " + n)
                .thenAccept(System.out::println)
                .join();  // Result: 10

        // Composing: thenCompose (flatMap)
        CompletableFuture<String> result = fetchUser(42L)
                .thenCompose(user -> fetchOrders(user));
        System.out.println(result.join());  // User-42 has 3 orders

        // Combining: thenCombine
        var f1 = CompletableFuture.supplyAsync(() -> "Hello");
        var f2 = CompletableFuture.supplyAsync(() -> "World");
        String combined = f1.thenCombine(f2, (a, b) -> a + " " + b).join();
        System.out.println(combined);  // Hello World

        // allOf — wait for multiple futures
        var futures = IntStream.range(1, 6)
                .mapToObj(i -> CompletableFuture.supplyAsync(() -> {
                    simulateDelay(100);
                    return i;
                }, CUSTOM_POOL))
                .toArray(CompletableFuture[]::new);

        var allDone = CompletableFuture.allOf(futures)
                .thenApply(v -> Stream.of(futures)
                        .map(CompletableFuture::join)
                        .toList());
        System.out.println(allDone.join());  // [1, 2, 3, 4, 5]

        // Error handling: exceptionally
        String safeResult = CompletableFuture
                .supplyAsync(() -> { throw new RuntimeException("Oops"); })
                .exceptionally(ex -> "Fallback: " + ex.getMessage())
                .join();
        System.out.println(safeResult);  // Fallback: Oops

        // Clean up
        CUSTOM_POOL.shutdown();
    }
}

```
