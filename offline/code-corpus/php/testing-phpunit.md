---
language: php
tags: [testing, pattern]
title: Testing (PHPUnit)
description: PHPUnit test cases: setUp, @test annotations, assertions, mocks, data providers.
source: pattern
---

```php
<?php

use PHPUnit\Framework\TestCase;
// use Mockery;
// use Mockery\Adapter\Phpunit\MockeryPHPUnitIntegration;

class UserService
{
    public function __construct(private PDO $pdo) {}

    public function getUserName(int $id): ?string
    {
        $stmt = $this->pdo->prepare('SELECT name FROM users WHERE id = ?');
        $stmt->execute([$id]);
        return $stmt->fetchColumn() ?: null;
    }
}

class UserServiceTest extends TestCase
{
    private PDO $pdo;
    private UserService $service;

    protected function setUp(): void
    {
        $this->pdo = new PDO('sqlite::memory:');
        $this->pdo->exec('CREATE TABLE users (id INTEGER, name TEXT)');
        $this->pdo->exec("INSERT INTO users VALUES (1, 'Alice')");
        $this->service = new UserService($this->pdo);
    }

    /** @test */
    public function it_returns_user_name_for_valid_id(): void
    {
        $name = $this->service->getUserName(1);
        $this->assertSame('Alice', $name);
    }

    /** @test */
    public function it_returns_null_for_missing_user(): void
    {
        $name = $this->service->getUserName(999);
        $this->assertNull($name);
    }

    // Data provider example
    /** @dataProvider userNameProvider */
    public function test_with_data_provider(int $id, ?string $expected): void
    {
        $result = $this->service->getUserName($id);
        $this->assertSame($expected, $result);
    }

    public static function userNameProvider(): array
    {
        return [
            [1, 'Alice'],
            [2, null],
        ];
    }
}

// --- Mocking example (PHPUnit built-in) ---
// class MailerTest extends TestCase
// {
//     /** @test */
//     public function it_sends_welcome_email(): void
//     {
//         $mailer = $this->createMock(Mailer::class);
//         $mailer->expects($this->once())
//                ->method('send')
//                ->with($this->stringContains('welcome'))
//                ->willReturn(true);
//
//         $service = new WelcomeService($mailer);
//         $service->sendWelcome('alice@example.com');
//     }
// }

// --- Mockery example ---
// class LoggerTest extends TestCase
// {
//     use MockeryPHPUnitIntegration;
//
//     /** @test */
//     public function it_logs_messages(): void
//     {
//         $logger = Mockery::mock(Logger::class);
//         $logger->shouldReceive('log')
//                ->once()
//                ->with('Hello')
//                ->andReturn(true);
//
//         $logger->log('Hello');
//     }
// }

```
