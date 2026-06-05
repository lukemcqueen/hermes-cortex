---
language: dart
tags: [dart, collections, list, set, map, spread, cascade, groupBy]
title: Collections
description: Dart List, Set, Map, spread (...), collection for/if, groupBy, cascade notation.
source: pattern
---

```dart
// ── List with collection-for and collection-if ──
List<int> buildList() {
  final numbers = [1, 2, 3, 4, 5];
  return [
    0,
    if (numbers.isNotEmpty) ...numbers,
    for (var i = 6; i <= 10; i++) i,
  ];
}

// ── Set ──
final uniqueNames = <String>{'alice', 'bob', 'alice', 'charlie'};
// → {'alice', 'bob', 'charlie'}

// ── Map operations ──
void mapDemo() {
  final scores = <String, int>{
    'alice': 95,
    'bob': 87,
    'charlie': 92,
  };

  // Spread
  final more = {'dave': 78, ...scores};

  // Map comprehension
  final doubled = scores.map((k, v) => MapEntry(k, v * 2));

  print('Alice: ${scores['alice']}');
  print('All: $more');
  print('Doubled: $doubled');
}

// ── groupBy (extension) ──
extension IterableGroupBy<T> on Iterable<T> {
  Map<K, List<T>> groupBy<K>(K Function(T) keyFn) {
    final map = <K, List<T>>{};
    for (final item in this) {
      final key = keyFn(item);
      map.putIfAbsent(key, () => []).add(item);
    }
    return map;
  }
}

// ── Cascade notation ──
List<int> cascadeDemo() {
  return <int>[]
    ..add(1)
    ..addAll([2, 3, 4])
    ..removeLast()
    ..insert(0, 0);
}

void main() {
  print(buildList()); // [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  print(uniqueNames); // {alice, bob, charlie}
  mapDemo();
  print([1, 1, 2, 2, 3].groupBy((n) => n.isEven ? 'even' : 'odd'));
  print(cascadeDemo()); // [0, 1, 2, 3]
}

```
