---
language: dart
tags: [dart, classes, oop, extends, mixin, abstract, factory, static]
title: Classes & OOP
description: Dart classes, constructors, extends, mixins, implements, abstract, factory, static, and late fields.
source: pattern
---

```dart
// ── Base class ──
abstract class Shape {
  double area();
  String describe() => 'Shape';
}

// ── Inheritance ──
class Circle extends Shape {
  final double radius;
  const Circle(this.radius);

  @override
  double area() => 3.14159 * radius * radius;

  @override
  String describe() => 'Circle(r=$radius)';
}

// ── Mixin ──
mixin Printable {
  void printInfo() => print('Info: $runtimeType');
}

mixin JsonSerializable on Shape {
  Map<String, dynamic> toJson();
}

// ── Using mixins ──
class Rectangle extends Shape with Printable, JsonSerializable {
  final double width, height;
  Rectangle(this.width, this.height);

  @override
  double area() => width * height;

  @override
  Map<String, dynamic> toJson() => {
    'type': 'rectangle',
    'width': width,
    'height': height,
  };
}

// ── Factory constructor ──
class Logger {
  static final Map<String, Logger> _cache = {};
  final String name;

  factory Logger(String name) {
    return _cache.putIfAbsent(name, () => Logger._internal(name));
  }

  Logger._internal(this.name);

  void log(String msg) => print('[$name] $msg');
}

// ── Static & late ──
class Config {
  static const String appName = 'DartApp';
  static int _counter = 0;

  late final List<int> data; // initialized later
  final int id;

  Config(this.data) : id = ++_counter;
}

void main() {
  final c = Circle(5);
  print('${c.describe()}: ${c.area()}');

  final r = Rectangle(3, 4);
  r.printInfo();
  print(r.toJson());

  final log1 = Logger('app');
  final log2 = Logger('app');
  print('Same instance: ${log1 == log2}'); // true
}

```
