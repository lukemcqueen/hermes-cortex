---
language: dart
tags: [dart, functions, closures, lambda, tear-off, typedef, higher-order]
title: Functions & Closures
description: Dart functions — anonymous functions, => syntax, tear-off, Function types, typedef, higher-order functions.
source: pattern
---

```dart
// ── typedef ──
typedef IntTransformer = int Function(int x);
typedef Comparator<T> = int Function(T a, T b);

// ── Higher-order function ──
List<int> transform(List<int> items, IntTransformer fn) {
  return items.map(fn).toList();
}

// ── Tear-off — using method reference ──
int triple(int x) => x * 3;

// ── Anonymous function / closure ──
Function makeMultiplier(int factor) {
  return (int x) => x * factor; // closure capturing 'factor'
}

// ── Function with positional & named params ──
String formatMessage(String msg, {String prefix = '>>', bool uppercase = false}) {
  var result = '$prefix $msg';
  return uppercase ? result.toUpperCase() : result;
}

// ── Records (Dart 3) ──
(String, int) lookup(String key) {
  // Simulated lookup returning a record
  return ('value for $key', 42);
}

void main() {
  // Tear-off
  final numbers = [1, 2, 3, 4, 5];
  final tripled = numbers.map(triple).toList();
  print(tripled); // [3, 6, 9, 12, 15]

  // Anonymous function
  final evens = numbers.where((n) => n.isEven).toList();
  print(evens); // [2, 4]

  // Closure
  final doubleIt = makeMultiplier(2);
  print(doubleIt(5)); // 10

  // Named parameters
  print(formatMessage('hello'));
  print(formatMessage('urgent', prefix: '!!!', uppercase: true));

  // Records
  final (val, code) = lookup('test');
  print('$val (code=$code)');

  // Function type variable
  IntTransformer combo = (x) => x * x + 1;
  print(combo(4)); // 17
}

```
