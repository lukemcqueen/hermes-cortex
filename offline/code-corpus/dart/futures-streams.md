---
language: dart
tags: [dart, async, future, stream, await, async*, yield]
title: Futures & Streams
description: Dart Future<T>, async/await, Stream<T>, listen, async* generators, yield, StreamController.
source: pattern
---

```dart
import 'dart:async';

// ── Future with async/await ──
Future<String> fetchData(String url) async {
  // Simulate network delay
  await Future.delayed(Duration(milliseconds: 100));
  return 'Data from $url';
}

// ── Stream with async* ──
Stream<int> countStream(int max) async* {
  for (var i = 1; i <= max; i++) {
    await Future.delayed(Duration(milliseconds: 50));
    yield i; // emit one value
  }
}

// ── StreamController (manual control) ──
Stream<int> createControlledStream() {
  final controller = StreamController<int>();
  var count = 0;

  Timer.periodic(Duration(milliseconds: 100), (timer) {
    count++;
    controller.add(count);
    if (count >= 5) {
      controller.close();
      timer.cancel();
    }
  });

  return controller.stream;
}

// ── Stream transformations ──
Stream<String> processStream(Stream<int> source) {
  return source
      .where((n) => n.isEven)
      .map((n) => 'Even: $n');
}

// ── Multiple await in a stream ──
Future<void> consumeStream(Stream<int> stream) async {
  await for (final value in stream) {
    print('Got: $value');
  }
}

void main() async {
  // Future
  final data = await fetchData('https://example.com');
  print(data);

  // Listen to stream
  final sub = countStream(3).listen(print);
  await Future.delayed(Duration(milliseconds: 200));
  sub.cancel();

  // Controlled stream
  final controlled = createControlledStream();
  await consumeStream(controlled);

  // Processed stream
  final processed = processStream(countStream(6));
  await consumeStream(processed);
}

```
