---
language: dart
tags: [dart, riverpod, state-management, provider, ref, flutter, family, autodispose]
title: Riverpod / State Management
description: Flutter Riverpod 2.x — Provider, StateNotifierProvider, ref.watch, ref.read, family, autodispose modifiers.
source: pattern
---

```dart
// Requires: flutter_riverpod, riverpod_annotation
// dart pub add flutter_riverpod riverpod_annotation
// dart pub add dev:riverpod_generator build_runner

import 'package:flutter_riverpod/flutter_riverpod.dart';

// ═══════════════════════════════════════════
// Simple Provider (sync value)
// ═══════════════════════════════════════════
final greetingProvider = Provider<String>((ref) {
  return 'Hello Riverpod!';
});

// ═══════════════════════════════════════════
// StateProvider (mutable simple state)
// ═══════════════════════════════════════════
final counterProvider = StateProvider<int>((ref) => 0);

// ═══════════════════════════════════════════
// FutureProvider (async data)
// ═══════════════════════════════════════════
final userProvider = FutureProvider<User>((ref) async {
  // Simulate network call
  await Future.delayed(const Duration(milliseconds: 200));
  return User(id: 1, name: 'Alice');
});

// ═══════════════════════════════════════════
// StateNotifierProvider (complex mutable state)
// ═══════════════════════════════════════════
class TodoListNotifier extends StateNotifier<List<Todo>> {
  TodoListNotifier() : super([]);

  void addTodo(String title) {
    state = [...state, Todo(id: state.length + 1, title: title)];
  }

  void toggleTodo(int id) {
    state = state.map((todo) {
      return todo.id == id ? todo.copyWith(done: !todo.done) : todo;
    }).toList();
  }

  void removeTodo(int id) {
    state = state.where((todo) => todo.id != id).toList();
  }
}

final todoListProvider = StateNotifierProvider<TodoListNotifier, List<Todo>>((ref) {
  return TodoListNotifier();
});

// ═══════════════════════════════════════════
// family — parameterized provider
// ═══════════════════════════════════════════
final todoDetailProvider = Provider.family<Todo?, int>((ref, id) {
  final todos = ref.watch(todoListProvider);
  return todos.where((t) => t.id == id).firstOrNull;
});

// ═══════════════════════════════════════════
// autodispose — cleanup when no longer watched
// ═══════════════════════════════════════════
final ephemeralProvider = FutureProvider.autoDispose<String>((ref) async {
  await Future.delayed(const Duration(seconds: 1));
  ref.onDispose(() => print('Disposed'));
  return 'Ephemeral';
});

// ═══════════════════════════════════════════
// Model classes
// ═══════════════════════════════════════════
class User {
  final int id;
  final String name;
  const User({required this.id, required this.name});
}

class Todo {
  final int id;
  final String title;
  final bool done;

  const Todo({required this.id, required this.title, this.done = false});

  Todo copyWith({int? id, String? title, bool? done}) {
    return Todo(
      id: id ?? this.id,
      title: title ?? this.title,
      done: done ?? this.done,
    );
  }
}

// ═══════════════════════════════════════════
// Widget usage (in Flutter)
// ═══════════════════════════════════════════
// class MyApp extends StatelessWidget {
//   @override
//   Widget build(BuildContext context) {
//     return ProviderScope(
//       child: MaterialApp(
//         home: Consumer(builder: (context, ref, _) {
//           final greeting = ref.watch(greetingProvider);
//           final counter = ref.watch(counterProvider);
//           return Scaffold(
//             body: Center(child: Text('$greeting Counter: $counter')),
//             floatingActionButton: FloatingActionButton(
//               onPressed: () => ref.read(counterProvider.notifier).state++,
//             ),
//           );
//         }),
//       ),
//     );
//   }
// }

```
