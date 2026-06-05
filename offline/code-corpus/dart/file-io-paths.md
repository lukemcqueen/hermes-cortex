---
language: dart
tags: [dart, file-io, file, directory, paths, dart-io, path-provider]
title: File I/O & Paths
description: Dart dart:io — File, Directory, RandomAccessFile, path_provider, FileSystemEntity.
source: pattern
---

```dart
import 'dart:io';

// ── Write & read text file ──
Future<void> writeAndRead(String path) async {
  final file = File(path);

  // Write
  await file.writeAsString('Hello from Dart!\nLine 2\n');

  // Read entire file
  final content = await file.readAsString();
  print('Content:\n$content');

  // Read as lines
  final lines = await file.readAsLines();
  print('Lines: $lines');
}

// ── Binary file ──
Future<void> writeBinary(String path) async {
  final file = File(path);
  final bytes = <int>[0xDE, 0xAD, 0xBE, 0xEF, 0x01, 0x02, 0x03, 0x04];
  await file.writeAsBytes(bytes);

  // RandomAccessFile for seeking
  final raf = await file.open(mode: FileMode.read);
  try {
    await raf.setPosition(2);
    final buf = await raf.read(4);
    print('Read at pos 2: ${buf.map((b) => b.toRadixString(16))}');
  } finally {
    await raf.close();
  }
}

// ── Directory operations ──
Future<void> directoryDemo(String dirPath) async {
  final dir = Directory(dirPath);

  // Create directory recursively
  if (!await dir.exists()) {
    await dir.create(recursive: true);
  }

  // List contents
  await for (final entity in dir.list(recursive: true, followLinks: false)) {
    final stat = await entity.stat();
    print('${entity.path} (${stat.type})');
  }

  // FileSystemEntity helpers
  final temp = Directory.systemTemp;
  print('Temp dir: ${temp.path}');
}

// ── path_provider (Flutter) ──
// In a Flutter project add path_provider package.
// import 'package:path_provider/path_provider.dart';
//
// Future<String> getAppDir() async {
//   final dir = await getApplicationDocumentsDirectory();
//   return dir.path;
// }

void main() async {
  await writeAndRead('example.txt');
  await writeBinary('example.bin');
  await directoryDemo('test_dir');

  // Cleanup
  await File('example.txt').delete();
  await File('example.bin').delete();
  await Directory('test_dir').delete(recursive: true);
}

```
