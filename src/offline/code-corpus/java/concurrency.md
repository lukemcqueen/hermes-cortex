---
language: java
tags: [pattern, concurrency]
title: Concurrency
description: Thread, Runnable, ExecutorService, CompletableFuture, synchronized, volatile, and ReentrantLock.
source: pattern
---

```java
import java.util.concurrent.*;
import java.util.concurrent.locks.*;
import java.util.stream.*;

public class ConcurrencyDemo {
    private static int sharedCounter = 0;
    private static final Lock lock = new ReentrantLock();

    static class CounterTask implements Runnable {
        private final int increments;

        CounterTask(int increments) {
            this.increments = increments;
        }

        @Override
        public void run() {
            for (int i = 0; i < increments; i++) {
                lock.lock();
                try {
                    sharedCounter++;
                } finally {
                    lock.unlock();
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        // Basic thread
        Thread t = new Thread(() -> System.out.println("Hello from thread"));
        t.start();
        t.join();

        // ExecutorService
        ExecutorService executor = Executors.newFixedThreadPool(4);
        var futures = IntStream.range(0, 10)
                .mapToObj(i -> executor.submit(() -> {
                    Thread.sleep(ThreadLocalRandom.current().nextInt(100));
                    return i * i;
                }))
                .toList();

        for (var f : futures) {
            System.out.println("Result: " + f.get());
        }
        executor.shutdown();

        // CompletableFuture
        CompletableFuture.supplyAsync(() -> "Hello")
                .thenApply(s -> s + " World")
                .thenAccept(System.out::println)
                .join();

        // synchronized block
        var sb = new StringBuffer();
        synchronized (sb) {
            sb.append("Thread-safe append");
        }

        // volatile: use for visibility flags
        class Runner {
            volatile boolean running = true;
        }
    }
}

```
