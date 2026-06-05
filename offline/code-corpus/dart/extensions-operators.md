---
language: dart
tags: [dart, extensions, operators, overloading, callable, custom-types]
title: Extensions & Operators
description: Dart extension methods on existing types, operator overloading, and callable classes.
source: pattern
---

```dart
// ── Extension on built-in type ──
extension IntSquared on int {
  int get squared => this * this;
  bool get isEven => this % 2 == 0;
}

// ── Extension on generic type ──
extension ListShuffle<T> on List<T> {
  List<T> shuffled() {
    final copy = [...this];
    copy.shuffle();
    return copy;
  }

  T? firstOrNull() => isEmpty ? null : first;
}

// ── Extension with operators ──
extension DurationMath on Duration {
  Duration operator *(int factor) => Duration(microseconds: inMicroseconds * factor);
  Duration operator +(Duration other) => Duration(microseconds: inMicroseconds + other.inMicroseconds);
}

// ── Operator overloading on custom class ──
class Vector2 {
  final double x, y;
  const Vector2(this.x, this.y);

  Vector2 operator +(Vector2 other) => Vector2(x + other.x, y + other.y);
  Vector2 operator -(Vector2 other) => Vector2(x - other.x, y - other.y);
  Vector2 operator *(double scalar) => Vector2(x * scalar, y * scalar);
  double operator [](int index) => index == 0 ? x : y;

  @override
  String toString() => 'Vector2($x, $y)';
}

// ── Callable class ──
class Multiplier {
  final int factor;
  const Multiplier(this.factor);

  int call(int value) => value * factor;
}

// ── Extension on enum ──
enum Status { pending, active, done }

extension StatusLabel on Status {
  String get label {
    return switch (this) {
      Status.pending => '⏳ Pending',
      Status.active => '✅ Active',
      Status.done => '✔ Completed',
    };
  }
}

void main() {
  print(5.squared); // 25
  print([1, 2, 3].shuffled());
  print([1, 2, 3].firstOrNull()); // 1
  print(<int>[].firstOrNull()); // null

  final v1 = Vector2(3, 4);
  final v2 = Vector2(1, 2);
  print(v1 + v2); // Vector2(4, 6)
  print(v1 * 2);   // Vector2(6, 8)
  print(v1[0]);    // 3.0

  final double = Multiplier(2);
  print(double(21)); // 42

  print(Status.pending.label);
  print(const Duration(seconds: 30) * 2); // 60 seconds
}

```
