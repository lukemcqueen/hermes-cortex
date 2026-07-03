---
language: java
tags: [pattern, architecture]
title: Modules & JPMS
description: module-info.java with exports/requires/opens/provides, and Module API introspection.
source: pattern
---

```java
// --- module-info.java for com.example.app ---
module com.example.app {
    // Dependencies
    requires com.example.service;
    requires com.fasterxml.jackson.databind;
    requires org.slf4j;

    // Package access
    exports com.example.app.api;
    exports com.example.app.dto;

    // Open for reflective access (Jackson, Hibernate, etc.)
    opens com.example.app.dto to com.fasterxml.jackson.databind;

    // Service provider
    provides com.example.app.spi.ReportGenerator
        with com.example.app.reporting.PdfReportGenerator;
}

// --- module-info.java for com.example.service ---
module com.example.service {
    exports com.example.service.api;

    // Qualified export — only visible to listed modules
    exports com.example.service.internal to com.example.app;
}

// --- Java code using Module API ---
import java.lang.module.ModuleDescriptor;
import java.util.stream.*;

public class JpmsDemo {
    public static void main(String[] args) {
        // Module API introspection
        Module myModule = JpmsDemo.class.getModule();
        System.out.println("Module name: " + myModule.getName());
        System.out.println("Is named: " + myModule.isNamed());
        System.out.println("Is exported: " +
                myModule.isExported("java.snippets"));

        // List exported packages
        ModuleDescriptor descriptor = myModule.getDescriptor();
        if (descriptor != null) {
            System.out.println("\nExported packages:");
            descriptor.exports().forEach(ex -> {
                System.out.println("  " + ex.source() +
                    (ex.isQualified()
                        ? " -> " + ex.targets().stream().collect(Collectors.joining(","))
                        : " (unqualified)"));
            });

            System.out.println("\nRequired modules:");
            descriptor.requires().forEach(req ->
                    System.out.println("  " + req.name() +
                            " (" + req.modifiers() + ")"));
        }

        // Boot layer modules (built-in)
        System.out.println("\nBoot layer modules (first 5):");
        ModuleLayer.boot().modules()
                .map(Module::getName)
                .limit(5)
                .forEach(System.out::println);
    }
}

```
