---
language: java
tags: [pattern, io]
title: File I/O (java.nio.file)
description: Reading/writing files, streaming lines, walking directories, Path and BufferedReader with try-resources.
source: pattern
---

```java
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

public class FileIODemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("demo.txt");

        // Write lines
        Files.writeString(path, "Hello\nWorld\nJava 17");

        // Read all lines
        List<String> lines = Files.readAllLines(path);
        lines.forEach(System.out::println);

        // Stream lines (lazy)
        try (Stream<String> stream = Files.lines(path)) {
            stream.filter(l -> l.startsWith("J"))
                  .forEach(System.out::println);  // Java 17
        }

        // Walk directory tree
        try (Stream<Path> walk = Files.walk(Path.of("."), 2)) {
            walk.filter(Files::isRegularFile)
                .forEach(p -> System.out.println(p + " (" + Files.size(p) + " bytes)"));
        }

        // BufferedReader with try-resources
        try (BufferedReader br = Files.newBufferedReader(
                Path.of("demo.txt"), java.nio.charset.StandardCharsets.UTF_8)) {
            br.lines().forEach(System.out::println);
        }

        // BufferedWriter
        try (BufferedWriter bw = Files.newBufferedWriter(
                Path.of("output.txt"))) {
            bw.write("Generated content");
            bw.newLine();
        }

        // Cleanup
        Files.deleteIfExists(path);
        Files.deleteIfExists(Path.of("output.txt"));
    }
}

```
