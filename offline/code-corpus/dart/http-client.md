---
language: dart
tags: [dart, http, client, rest, api, json, request]
title: HTTP Client
description: Dart HTTP — http package and dart:io HttpClient, GET/POST, headers, JSON response, error handling.
source: pattern
---

```dart
import 'dart:convert';
import 'dart:io';

// ── Using dart:io HttpClient ──
Future<Map<String, dynamic>> fetchViaHttpClient(String url) async {
  final client = HttpClient();
  try {
    final request = await client.getUrl(Uri.parse(url));
    request.headers.set('Accept', 'application/json');

    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();

    if (response.statusCode == 200) {
      return jsonDecode(body) as Map<String, dynamic>;
    } else {
      throw HttpException(
        'Request failed: ${response.statusCode}',
        uri: Uri.parse(url),
      );
    }
  } finally {
    client.close();
  }
}

// ── Using http package (pub.dev) ──
// Add dependency: dart pub add http
// import 'package:http/http.dart' as http;

Future<Map<String, dynamic>> fetchViaHttpPackage(String url) async {
  // final response = await http.get(Uri.parse(url));
  // if (response.statusCode == 200) {
  //   return jsonDecode(response.body) as Map<String, dynamic>;
  // }
  // throw Exception('Status: ${response.statusCode}');
  throw UnimplementedError('Add http package to use this');
}

// ── POST request ──
Future<Map<String, dynamic>> postJson(String url, Map<String, dynamic> data) async {
  final client = HttpClient();
  try {
    final request = await client.postUrl(Uri.parse(url));
    request.headers.contentType = ContentType.json;
    request.headers.set('Authorization', 'Bearer token123');
    request.write(jsonEncode(data));

    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();

    if (response.statusCode == 201 || response.statusCode == 200) {
      return jsonDecode(body) as Map<String, dynamic>;
    }
    throw HttpException('POST failed: ${response.statusCode}', uri: Uri.parse(url));
  } finally {
    client.close();
  }
}

// ── Response model ──
class ApiResponse {
  final int statusCode;
  final Map<String, dynamic>? data;
  final String? error;

  const ApiResponse({required this.statusCode, this.data, this.error});

  bool get isSuccess => statusCode >= 200 && statusCode < 300;
}

Future<ApiResponse> safeRequest(String url) async {
  try {
    return ApiResponse(statusCode: 200, data: await fetchViaHttpClient(url));
  } on SocketException catch (e) {
    return ApiResponse(statusCode: 0, error: 'Network error: $e');
  } on HttpException catch (e) {
    return ApiResponse(statusCode: -1, error: e.message);
  }
}

void main() async {
  // Example: fetchViaHttpClient('https://api.github.com/zen');
  // Example: postJson('https://httpbin.org/post', {'key': 'value'});

  // Safe request
  final result = await safeRequest('https://jsonplaceholder.typicode.com/todos/1');
  if (result.isSuccess) {
    print('Data: ${result.data}');
  } else {
    print('Error: ${result.error}');
  }
}

```
