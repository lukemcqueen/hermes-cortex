---
language: dart
tags: [dart, errors, exceptions, try, catch, finally, rethrow]
title: Error Handling
description: Dart exception handling — try/on/catch/finally, rethrow, custom Exception classes, StackTrace.
source: pattern
---

```dart
// ── Custom exception ──
class ValidationException implements Exception {
  final String message;
  final String field;
  const ValidationException(this.message, this.field);

  @override
  String toString() => 'ValidationException($field): $message';
}

// ── Function that throws ──
int parseAge(String input) {
  final age = int.tryParse(input);
  if (age == null) {
    throw const FormatException('Invalid number');
  }
  if (age < 0 || age > 150) {
    throw ValidationException('Age out of range', 'age');
  }
  return age;
}

// ── Multiple catch clauses ──
void processAge(String input) {
  try {
    final age = parseAge(input);
    print('Age is $age');
  } on FormatException catch (e) {
    print('Format error: ${e.message}');
  } on ValidationException catch (e) {
    print('Validation error on ${e.field}: ${e.message}');
  } catch (e, stack) {
    // Generic catch with stack trace
    print('Unexpected error: $e');
    print('Stack: $stack');
  } finally {
    print('Finished processing age');
  }
}

// ── Rethrow pattern ──
void rethrowDemo(String input) {
  try {
    processAge(input);
  } catch (e) {
    // Log and rethrow
    print('[LOG] Error occurred: $e');
    rethrow; // preserves original stack trace
  }
}

// ── tryParse pattern (no exception) ──
int? safeParseAge(String input) {
  try {
    return parseAge(input);
  } on Exception {
    return null;
  }
}

// ── assert for internal invariants ──
int divide(int a, int b) {
  assert(b != 0, 'Division by zero');
  return a ~/ b;
}

void main() {
  processAge('25');  // OK
  processAge('abc'); // FormatException
  processAge('200'); // ValidationException

  print('Safe: ${safeParseAge('25')}');
  print('Safe: ${safeParseAge('invalid')}');
}

```
