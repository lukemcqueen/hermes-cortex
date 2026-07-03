---
language: java
tags: [pattern, logging]
title: Logging (SLF4J + Logback)
description: LoggerFactory, log levels, MDC for contextual logging, parameterized messages, logback.xml config.
source: pattern
---

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class LoggingDemo {
    // SLF4J logger — no direct Logback dependency in code
    private static final Logger log = LoggerFactory.getLogger(LoggingDemo.class);

    public static void main(String[] args) {
        // Parameterized logging (avoids string concatenation)
        String user = "Alice";
        int count = 42;
        log.info("User {} has {} items in cart", user, count);
        log.debug("Processing order for user: {}", user);

        // Error logging with exception
        try {
            riskyOperation();
        } catch (Exception e) {
            log.error("Operation failed for user {}", user, e);
        }

        // MDC (Mapped Diagnostic Context) — per-thread context
        MDC.put("requestId", "req-" + System.currentTimeMillis());
        MDC.put("userId", user);
        log.info("Processing payment");
        processPayment();
        MDC.clear();

        // Level-specific checks (useful for expensive log construction)
        if (log.isTraceEnabled()) {
            log.trace("Expensive detail: {}", expensiveCall());
        }
    }

    static void riskyOperation() {
        throw new RuntimeException("Timeout");
    }

    static String expensiveCall() {
        return "expensive-result";
    }

    static void processPayment() {
        // MDC is inherited by the current thread
        Logger paymentLog = LoggerFactory.getLogger("payment");
        paymentLog.info("Payment processed");
    }
}

// --- src/main/resources/logback.xml ---
/*
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} [%X{requestId}] — %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/app.%d{yyyy-MM-dd}.log</fileNamePattern>
            <maxHistory>30</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} [%thread] %-5level %logger{36} — %msg%n</pattern>
        </encoder>
    </appender>

    <root level="info">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>

    <logger name="payment" level="debug" additivity="false">
        <appender-ref ref="CONSOLE"/>
    </logger>
</configuration>
*/

```
