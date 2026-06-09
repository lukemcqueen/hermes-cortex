---
language: php
tags: [architecture, pattern]
title: Dependency Injection
description: PSR-11 container pattern, constructor injection, service providers, and autowiring.
source: pattern
---

```php
<?php

// PSR-11 ContainerInterface
interface ContainerInterface {
    public function get(string $id): mixed;
    public function has(string $id): bool;
}

// Simple DI container with autowiring support
class Container implements ContainerInterface {
    private array $bindings   = [];
    private array $instances  = [];
    private array $providers  = [];

    public function set(string $id, callable|object $factory): void {
        $this->bindings[$id] = $factory;
    }

    public function get(string $id): mixed {
        if (isset($this->instances[$id])) {
            return $this->instances[$id];
        }
        if (isset($this->bindings[$id])) {
            $factory = $this->bindings[$id];
            if (is_callable($factory)) {
                $instance = $factory($this);
            } else {
                $instance = $factory;
            }
            $this->instances[$id] = $instance;
            return $instance;
        }
        // Autowiring attempt
        return $this->autowire($id);
    }

    public function has(string $id): bool {
        return isset($this->bindings[$id])
            || isset($this->instances[$id])
            || class_exists($id);
    }

    public function registerProvider(callable $provider): void {
        $provider($this);
    }

    private function autowire(string $class): object {
        $ref = new ReflectionClass($class);
        $constructor = $ref->getConstructor();
        if ($constructor === null) {
            return $ref->newInstance();
        }
        $deps = [];
        foreach ($constructor->getParameters() as $param) {
            $type = $param->getType();
            if ($type instanceof ReflectionNamedType && !$type->isBuiltin()) {
                $deps[] = $this->get($type->getName());
            } else {
                $deps[] = $param->isDefaultValueAvailable()
                    ? $param->getDefaultValue()
                    : throw new RuntimeException("Cannot resolve {$param->getName()}");
            }
        }
        return $ref->newInstanceArgs($deps);
    }
}

// Service provider pattern
class LoggerService {
    public function log(string $msg): void {
        echo "[LOG] {$msg}\n";
    }
}

class UserRepository {
    public function __construct(private LoggerService $logger) {}
    public function find(int $id): string {
        $this->logger->log("Finding user #{$id}");
        return "User #{$id}";
    }
}

// --- Usage ---
// $container = new Container();
// $container->set(LoggerService::class, fn() => new LoggerService());
// // UserRepository is autowired
//
// $repo = $container->get(UserRepository::class);
// echo $repo->find(42);

```
