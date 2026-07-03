---
language: dart
tags: [dart, null-safety, nullable, late, required, assertion]
title: Null Safety
description: Dart 3 null safety — !, ?, late, required, Object?, assertion, null-aware operators.
source: pattern
---

```dart
// ── Nullable types ──
String? maybeName(String? input) {
  return input?.toUpperCase(); // null-aware call
}

// ── Non-null assertion ──
int parseLenient(String? s) {
  // ! — asserts not null at runtime
  return s!.length;
}

// ── late — non-nullable but initialized later ──
class Database {
  late final List<String> records; // initialized before first use

  void load() {
    records = ['a', 'b', 'c'];
  }

  int get count => records.length;
}

// ── required named parameters ──
class Point {
  final double x, y;
  const Point({required this.x, required this.y});
}

// ── Object? — nullable root ──
void printType(Object? obj) {
  if (obj is int) {
    print('int: ${obj}');
  } else if (obj is String) {
    print('String: $obj');
  } else {
    print('unknown: $obj');
  }
}

// ── Null-aware operators ──
void nullAwareDemo() {
  String? a;
  String b = 'hello';

  // ?. — call only if non-null
  final len = a?.length;

  // ?? — provide default
  final name = a ?? 'default';

  // ??= — assign if null
  a ??= b;

  // Cascade with null-aware
  final list = <int>[];
  list
    ..add(1)
    ..add(2);

  // Assertion
  assert(a != null, 'a should not be null');
}

void main() {
  final db = Database();
  db.load();
  print('count: ${db.count}');
  print(maybeName('dart'));
  printType(42);
}

```
