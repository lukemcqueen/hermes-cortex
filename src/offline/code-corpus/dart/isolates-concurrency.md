---
language: dart
tags: [dart, isolates, concurrency, Isolate, send-port, receive-port, compute]
title: Isolates & Concurrency
description: Dart Isolate concurrency — Isolate.spawn, SendPort/ReceivePort, Flutter compute, Isolate.run.
source: pattern
---

```dart
import 'dart:async';
import 'dart:isolate';

// ── Worker function that receives a SendPort ──
void worker(SendPort sendPort) {
  sendPort.send('Hello from isolate!');
}

// ── Worker with request/response pattern ──
void calculator(SendPort sendPort) {
  final receivePort = ReceivePort();
  sendPort.send(receivePort.sendPort);

  receivePort.listen((message) {
    if (message is Map<String, dynamic>) {
      final a = message['a'] as int;
      final b = message['b'] as int;
      sendPort.send({'result': a + b});
    }
  });
}

// ── Heavy computation function (for Flutter compute) ──
int fibonacci(int n) {
  if (n <= 1) return n;
  return fibonacci(n - 1) + fibonacci(n - 2);
}

// ── Isolate.run (Dart 2.19+) ──
Future<int> runInIsolate(int n) async {
  return await Isolate.run(() => fibonacci(n));
}

// ── Complete Isolate lifecycle ──
Future<void> isolateDemo() async {
  // Simple spawn
  {
    final receivePort = ReceivePort();
    await Isolate.spawn(worker, receivePort.sendPort);
    final msg = await receivePort.first;
    print('Got: $msg');
  }

  // Request/response pattern
  {
    final receivePort = ReceivePort();
    final isolate = await Isolate.spawn(calculator, receivePort.sendPort);
    final workerSendPort = await receivePort.first as SendPort;

    final resultPort = ReceivePort();
    workerSendPort.send({'a': 10, 'b': 32});

    // Listen for results
    resultPort.listen((msg) {
      print('Result: $msg');
    });

    // Cleanup
    resultPort.close();
    isolate.kill(priority: Isolate.immediate);
  }

  // Isolate.run — simple
  {
    final result = await runInIsolate(40);
    print('fib(40) = $result');
  }
}

void main() async {
  await isolateDemo();
}

```
