---
language: java
tags: [pattern, util]
title: Enums & Pattern Matching
description: Enum with fields/methods, switch expressions, pattern matching for switch (Java 17+), and yield.
source: pattern
---

```java
// Enum with fields and methods
enum HttpStatus {
    OK(200, "OK"),
    CREATED(201, "Created"),
    NOT_FOUND(404, "Not Found"),
    INTERNAL_SERVER_ERROR(500, "Internal Server Error");

    private final int code;
    private final String reason;

    HttpStatus(int code, String reason) {
        this.code = code;
        this.reason = reason;
    }

    public int code() { return code; }
    public String reason() { return reason; }

    public boolean isError() {
        return code >= 400;
    }

    public static HttpStatus fromCode(int code) {
        for (var s : values()) {
            if (s.code == code) return s;
        }
        throw new IllegalArgumentException("Unknown code: " + code);
    }
}

// Sealed interface for pattern matching
sealed interface Payment permits Cash, Card, Transfer {}
record Cash(double amount) implements Payment {}
record Card(String cardNumber, double amount) implements Payment {}
record Transfer(String iban, double amount) implements Payment {}

public class EnumPatternDemo {
    // Switch expression with pattern matching (Java 17+ preview, Java 21+ stable)
    static String describePayment(Payment p) {
        return switch (p) {
            case Cash c -> "Cash: $" + c.amount();
            case Card c -> "Card ****" + c.cardNumber().substring(c.cardNumber().length() - 4)
                           + ": $" + c.amount();
            case Transfer t -> "Transfer to IBAN " + t.iban() + ": $" + t.amount();
        };
    }

    static String describeStatus(HttpStatus s) {
        return switch (s) {
            case OK       -> "Success";
            case CREATED  -> "Created";
            case NOT_FOUND -> "Not Found (404)";
            default      -> {
                String msg = s.code() + " " + s.reason();
                yield msg + " — " + (s.isError() ? "Error" : "Info");
            }
        };
    }

    public static void main(String[] args) {
        System.out.println(HttpStatus.OK.code());                       // 200
        System.out.println(HttpStatus.fromCode(404).reason());           // Not Found

        System.out.println(describePayment(new Cash(25.50)));            // Cash: $25.5
        System.out.println(describePayment(new Card("1234567890123456", 99.99)));

        System.out.println(describeStatus(HttpStatus.CREATED));
        System.out.println(describeStatus(HttpStatus.INTERNAL_SERVER_ERROR));
    }
}

```
