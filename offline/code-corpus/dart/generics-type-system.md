---
language: dart
tags: [dart, generics, type-system, covariant, typedef, type-bounds]
title: Generics & Type System
description: Dart generics — generic classes/methods, type bounds (extends), covariant, typedef with generics.
source: pattern
---

```dart
// ── Generic class with type bound ──
class Box<T extends num> {
  final T value;
  const Box(this.value);

  Box<T> operator +(Box<T> other) => Box<T>((value + other.value) as T);
}

// ── Generic method ──
T firstOrElse<T>(List<T> items, T fallback) {
  return items.isNotEmpty ? items.first : fallback;
}

// ── Type bounds with interfaces ──
abstract class Jsonable {
  Map<String, dynamic> toJson();
}

class Repository<T extends Jsonable> {
  final List<T> _items = [];

  void add(T item) => _items.add(item);
  List<Map<String, dynamic>> exportAll() => _items.map((e) => e.toJson()).toList();
}

// ── covariant keyword ──
class Animal {
  void feed(covariant String food) => print('Fed $food');
}

class Dog extends Animal {
  @override
  void feed(String food) => print('Dog ate $food');
}

// ── typedef with generics ──
typedef Mapper<T, R> = R Function(T input);
typedef StreamTransformer<T> = Stream<T> Function(Stream<T> source);

// ── Using generics ──
void genericDemo() {
  final intBox = Box<int>(42);
  final result = intBox + Box<int>(8);
  print('Sum: ${result.value}'); // 50

  print(firstOrElse<String>([], 'default')); // default
  print(firstOrElse<int>([1, 2], -1));       // 1
}

// ── Type inference ──
var inferredList = [1, 2, 3]; // List<int>
final map = <String, dynamic>{'key': 'value'}; // explicit

// ── Multiple type parameters ──
class Pair<A, B> {
  final A first;
  final B second;
  const Pair(this.first, this.second);
}

void main() {
  genericDemo();

  final pair = Pair<String, int>('hello', 42);
  print('${pair.first}: ${pair.second}');

  final upperCase = const Mapper<String, String>((s) => s.toUpperCase());
  print(upperCase('hello'));
}

```
