---
language: php
tags: [api, pattern]
title: REST API
description: Plain PHP REST API router with JSON responses, CORS, input validation, and error handling.
source: pattern
---

```php
<?php

// CORS headers
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// Simple router
function jsonResponse(mixed $data, int $code = 200): void {
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

function jsonError(string $message, int $code = 400): void {
    jsonResponse(['error' => $message], $code);
}

function getRoute(): array {
    $uri    = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
    $method = $_SERVER['REQUEST_METHOD'];
    return [$method, $uri];
}

function getJsonBody(): array {
    $body = file_get_contents('php://input');
    $data = json_decode($body, true);
    return is_array($data) ? $data : [];
}

// Input validation helper
function validate(array $data, array $rules): array {
    $errors = [];
    foreach ($rules as $field => $rule) {
        if (!isset($data[$field]) && str_contains($rule, 'required')) {
            $errors[$field][] = "{$field} is required";
        }
    }
    return $errors;
}

// --- Route handling ---
[$method, $uri] = getRoute();

try {
    match (true) {
        $method === 'GET' && $uri === '/api/users' => (function () {
            // Fetch users…
            jsonResponse(['users' => [['id' => 1, 'name' => 'Alice']]]);
        })(),

        $method === 'POST' && $uri === '/api/users' => (function () {
            $data = getJsonBody();
            $errors = validate($data, ['name' => 'required', 'email' => 'required']);
            if (!empty($errors)) {
                jsonError('Validation failed', 422);
            }
            // Create user…
            jsonResponse(['id' => 2, 'name' => $data['name']], 201);
        })(),

        default => jsonError('Not Found', 404),
    };
} catch (Throwable $e) {
    error_log($e->getMessage());
    jsonError('Internal Server Error', 500);
}

```
