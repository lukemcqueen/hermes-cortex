---
language: dart
tags: [dart, testing, test, group, expect, mockito, flutter-test, setUp]
title: Testing
description: Dart testing with test package — test, group, expect, setUp, mockito, and flutter_test WidgetTester.
source: pattern
---

```dart
import 'package:test/test.dart';

// ── Functions to test ──
int add(int a, int b) => a + b;

Future<String> fetchGreeting(String name) async {
  await Future.delayed(const Duration(milliseconds: 10));
  return 'Hello, $name!';
}

// ── Basic tests ──
void main() {
  group('add()', () {
    test('returns sum of positive numbers', () {
      expect(add(2, 3), equals(5));
    });

    test('handles negative numbers', () {
      expect(add(-1, 1), equals(0));
      expect(add(-5, -3), equals(-8));
    });
  });

  group('fetchGreeting()', () {
    test('returns expected greeting', () async {
      final result = await fetchGreeting('Dart');
      expect(result, 'Hello, Dart!');
    });
  });

  // ── setUp / tearDown ──
  group('with setup', () {
    late List<int> data;

    setUp(() {
      data = [1, 2, 3, 4, 5];
    });

    tearDown(() {
      // cleanup if needed
    });

    test('data is populated', () {
      expect(data.length, 5);
    });

    test('data contains 3', () {
      expect(data, contains(3));
    });
  });

  // ── Matchers ──
  group('matchers', () {
    test('string matchers', () {
      expect('hello world', startsWith('hello'));
      expect('hello world', endsWith('world'));
      expect('hello world', contains('lo wo'));
    });

    test('collection matchers', () {
      expect([1, 2, 3], hasLength(3));
      expect([1, 2, 3], everyElement(isLessThan(10)));
      expect([1, 2, 3], unorderedEquals([3, 1, 2]));
    });

    test('throws matcher', () {
      expect(() => throw Exception('bad'), throwsException);
      expect(() => throw ArgumentError('nope'), throwsArgumentError);
    });
  });
}

// ── Mockito example ──
// Requires mockito package: dart pub add mockito
//
// class MockDatabase extends Mock implements Database {}
//
// void main() {
//   test('calls fetch', () {
//     final db = MockDatabase();
//     when(db.getUser(1)).thenReturn(User(id: 1, name: 'Alice'));
//     expect(db.getUser(1).name, 'Alice');
//   });
// }

// ── flutter_test WidgetTester ──
// Requires flutter_test package.
//
// void main() {
//   testWidgets('Counter increments', (tester) async {
//     await tester.pumpWidget(const CounterWidget());
//     expect(find.text('Count: 0'), findsOneWidget);
//     await tester.tap(find.byType(ElevatedButton));
//     await tester.pump();
//     expect(find.text('Count: 1'), findsOneWidget);
//   });
// }

```
