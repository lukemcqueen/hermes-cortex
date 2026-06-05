---
language: dart
tags: [dart, flutter, widgets, material, stateful, stateless, listview]
title: Flutter Widgets
description: Flutter Material Design widgets — StatelessWidget, StatefulWidget, MaterialApp, Scaffold, Column, Row, ListView.
source: pattern
---

```dart
import 'package:flutter/material.dart';

// ── StatelessWidget ──
class GreetingTile extends StatelessWidget {
  final String name;
  const GreetingTile({super.key, required this.name});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text('Hello, $name!', style: Theme.of(context).textTheme.headlineSmall),
      ),
    );
  }
}

// ── StatefulWidget ──
class CounterWidget extends StatefulWidget {
  const CounterWidget({super.key});
  @override
  State<CounterWidget> createState() => _CounterWidgetState();
}

class _CounterWidgetState extends State<CounterWidget> {
  int _count = 0;

  void _increment() => setState(() => _count++);

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('Count: $_count', style: const TextStyle(fontSize: 24)),
        const SizedBox(height: 8),
        ElevatedButton(onPressed: _increment, child: const Text('+1')),
      ],
    );
  }
}

// ── App ──
class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Demo',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const MyHomePage(),
    );
  }
}

class MyHomePage extends StatelessWidget {
  const MyHomePage({super.key});

  @override
  Widget build(BuildContext context) {
    final items = List.generate(20, (i) => 'Item $i');

    return Scaffold(
      appBar: AppBar(title: const Text('Flutter Widgets')),
      body: ListView.builder(
        itemCount: items.length,
        itemBuilder: (context, index) {
          return ListTile(
            leading: CircleAvatar(child: Text('${index + 1}')),
            title: Text(items[index]),
          );
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Pressed!')),
          );
        },
        child: const Icon(Icons.add),
      ),
    );
  }
}

```
