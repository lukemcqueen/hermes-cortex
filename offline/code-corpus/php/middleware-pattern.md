---
language: php
tags: [architecture, pattern]
title: Middleware Pattern
description: PSR-15 style middleware: request handler chain, before/after, logging and auth middleware.
source: pattern
---

```php
<?php

// PSR-7 and PSR-15 style middleware pattern (minimal implementation)

interface ServerRequestInterface {}
interface ResponseInterface {}
class Request implements ServerRequestInterface {}
class Response implements ResponseInterface {
    public function __construct(
        private string $body = '',
        private int $status = 200,
        private array $headers = [],
    ) {}
    public function withHeader(string $name, string $value): static {
        $this->headers[$name] = $value;
        return $this;
    }
    public function getBody(): string { return $this->body; }
    public function getStatusCode(): int { return $this->status; }
}

interface RequestHandlerInterface {
    public function handle(ServerRequestInterface $request): ResponseInterface;
}

interface MiddlewareInterface {
    public function process(
        ServerRequestInterface $request,
        RequestHandlerInterface $handler,
    ): ResponseInterface;
}

// Core request handler
class RequestHandler implements RequestHandlerInterface {
    /** @var MiddlewareInterface[] */
    private array $middlewares = [];
    private int $index = 0;

    public function __construct(
        private readonly callable $coreHandler,
    ) {}

    public function add(MiddlewareInterface $middleware): void {
        $this->middlewares[] = $middleware;
    }

    public function handle(ServerRequestInterface $request): ResponseInterface {
        if (isset($this->middlewares[$this->index])) {
            $middleware = $this->middlewares[$this->index];
            $this->index++;
            return $middleware->process($request, $this);
        }
        return ($this->coreHandler)($request);
    }
}

// --- Concrete Middlewares ---

class LoggingMiddleware implements MiddlewareInterface {
    public function process(
        ServerRequestInterface $request,
        RequestHandlerInterface $handler,
    ): ResponseInterface {
        error_log('Request started at ' . microtime(true));
        $response = $handler->handle($request);
        error_log('Request finished at ' . microtime(true));
        return $response;
    }
}

class AuthMiddleware implements MiddlewareInterface {
    public function __construct(private readonly string $apiKey) {}

    public function process(
        ServerRequestInterface $request,
        RequestHandlerInterface $handler,
    ): ResponseInterface {
        // Check auth header…
        // if (!$valid) { return new Response('Unauthorized', 401); }
        return $handler->handle($request);
    }
}

// --- Usage ---
// $handler = new RequestHandler(fn(Request $req) => new Response('Hello'));
// $handler->add(new LoggingMiddleware());
// $handler->add(new AuthMiddleware('secret'));
// $response = $handler->handle(new Request());

```
