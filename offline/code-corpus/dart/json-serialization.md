---
language: dart
tags: [dart, json, serialization, fromJson, toJson, freezed, dart-convert]
title: JSON & Serialization
description: Dart JSON handling — jsonDecode, jsonEncode, fromJson/toJson, freezed pattern, dart:convert.
source: pattern
---

```dart
import 'dart:convert';

// ── Manual JSON serialization ──
class User {
  final String name;
  final int age;
  final List<String> roles;

  const User({
    required this.name,
    required this.age,
    this.roles = const [],
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      name: json['name'] as String,
      age: json['age'] as int,
      roles: (json['roles'] as List<dynamic>?)?.cast<String>() ?? [],
    );
  }

  Map<String, dynamic> toJson() => {
    'name': name,
    'age': age,
    'roles': roles,
  };
}

// ── Freezed-like pattern using records (Dart 3) ──
// (Full freezed requires code-gen; this is a hand-written equivalent)
sealed class ApiResult<T> {
  const ApiResult();
}

class Success<T> extends ApiResult<T> {
  final T data;
  const Success(this.data);
}

class Failure<T> extends ApiResult<T> {
  final String message;
  final int? statusCode;
  const Failure(this.message, [this.statusCode]);
}

// ── JSON utilities ──
class JsonHelper {
  static String prettyEncode(Map<String, dynamic> data) {
    const encoder = JsonEncoder.withIndent('  ');
    return encoder.convert(data);
  }

  static T? safeDecode<T>(String json, T Function(Map<String, dynamic>) fromJson) {
    try {
      final map = jsonDecode(json) as Map<String, dynamic>;
      return fromJson(map);
    } catch (_) {
      return null;
    }
  }
}

void main() {
  // Encode
  final user = User(name: 'Alice', age: 30, roles: ['admin', 'editor']);
  final json = jsonEncode(user.toJson());
  print(json);

  // Decode
  final decoded = User.fromJson(jsonDecode(json) as Map<String, dynamic>);
  print('${decoded.name}, ${decoded.age}');

  // Pretty print
  print(JsonHelper.prettyEncode(user.toJson()));

  // Safe decode
  final parsed = JsonHelper.safeDecode('{"name":"Bob","age":25}', User.fromJson);
  print(parsed?.name);
}

```
