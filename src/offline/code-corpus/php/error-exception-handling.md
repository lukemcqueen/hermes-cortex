---
language: php
tags: [error, pattern]
title: Error & Exception Handling
description: Try/catch, set_exception_handler, error_reporting levels, custom exception classes, throwable.
source: pattern
---

```php
<?php

// Custom exception class
class ValidationException extends \RuntimeException
{
    public function __construct(
        string $message = 'Validation failed',
        int $code = 422,
        ?\Throwable $previous = null,
        public readonly array $errors = [],
    ) {
        parent::__construct($message, $code, $previous);
    }
}

class NotFoundException extends \RuntimeException
{
    public function __construct(string $resource = 'Resource')
    {
        parent::__construct("{$resource} not found", 404);
    }
}

// Global exception handler
set_exception_handler(function (\Throwable $e): void {
    $code = $e->getCode();
    if ($code < 100 || $code > 599) {
        $code = 500;
    }
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode([
        'error'   => $e->getMessage(),
        'code'    => $code,
        'file'    => $e->getFile(),
        'line'    => $e->getLine(),
    ]);
});

// Error-to-exception conversion
set_error_handler(function (
    int $severity,
    string $message,
    string $file,
    int $line,
): bool {
    if (!(error_reporting() & $severity)) {
        return false;
    }
    throw new \ErrorException($message, 0, $severity, $file, $line);
});

// Error reporting levels
// error_reporting(E_ALL);
// error_reporting(E_ALL & ~E_DEPRECATED & ~E_USER_DEPRECATED);
// ini_set('display_errors', '0');
// ini_set('log_errors', '1');

// Usage
try {
    $input = $_GET['id'] ?? throw new ValidationException('ID required');
    $id = (int) $input;
    if ($id <= 0) {
        throw new NotFoundException('User');
    }
    echo "Processing user #{$id}";
} catch (ValidationException $e) {
    echo "Validation: {$e->getMessage()}";
} catch (NotFoundException $e) {
    echo "Not found: {$e->getMessage()}";
} catch (\Throwable $e) {
    echo "Unexpected: {$e->getMessage()}";
} finally {
    echo " (done)";
}

```
