---
language: java
tags: [pattern, util]
title: Exception Handling
description: Try-catch-finally, try-with-resources, multi-catch, checked vs unchecked exceptions, custom exceptions.
source: pattern
---

```java
import java.io.*;

// Custom checked exception
class InsufficientFundsException extends Exception {
    public InsufficientFundsException(String message) {
        super(message);
    }
}

// Custom unchecked exception
class AccountNotFoundException extends RuntimeException {
    public AccountNotFoundException(String id) {
        super("Account not found: " + id);
    }
}

public class BankTransfer {
    public static void transfer(String fromId, double amount)
            throws InsufficientFundsException {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (amount > 1000) {
            throw new InsufficientFundsException("Insufficient funds: " + amount);
        }
        System.out.println("Transferred $" + amount);
    }

    public static void main(String[] args) {
        // Multi-catch
        try {
            transfer("ACC-001", 2000);
        } catch (InsufficientFundsException | IllegalArgumentException e) {
            System.err.println("Transfer error: " + e.getMessage());
        } finally {
            System.out.println("Transfer attempt finished");
        }

        // Try-with-resources (auto-closeable)
        try (BufferedReader br = new BufferedReader(
                new StringReader("Hello\nWorld"))) {
            String line;
            while ((line = br.readLine()) != null) {
                System.out.println(line);
            }
        } catch (IOException e) {
            System.err.println("IO error: " + e.getMessage());
        }

        // Checked vs unchecked
        throw new AccountNotFoundException("ACC-999");  // runtime, no throws needed
    }
}

```
