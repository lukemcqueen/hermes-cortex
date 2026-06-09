"""PHP (15) + Ruby (15) snippet modules combined in one file."""

SNIPPETS = [
    # ============================================================
    # PHP SNIPPETS (1-15)
    # ============================================================
    # 1. Classes & OOP
    (
        "php/classes-oop.md",
        "php",
        ["oop", "pattern"],
        "Classes & OOP",
        "PHP 8.x object-oriented features: readonly properties, constructor promotion, enums, interfaces, traits.",
        "pattern",
        """<?php

// Readonly class with constructor promotion (PHP 8.1+)
readonly class User {
    public function __construct(
        public string $name,
        public string $email,
        public Address $address,
    ) {}
}

// Enum (PHP 8.1+)
enum Role: string {
    case Admin = 'admin';
    case Editor = 'editor';
    case Viewer = 'viewer';
}

// Interface
interface Notifiable {
    public function notify(string $message): void;
}

// Trait
trait ValidatesEmail {
    public function isValidEmail(string $email): bool {
        return filter_var($email, FILTER_VALIDATE_EMAIL) !== false;
    }
}

// Class implementing interface, using trait
class AdminUser extends User implements Notifiable {
    use ValidatesEmail;

    public function __construct(
        string $name,
        string $email,
        Address $address,
        public Role $role = Role::Admin,
    ) {
        parent::__construct($name, $email, $address);
    }

    public function notify(string $message): void {
        if ($this->isValidEmail($this->email)) {
            mail($this->email, 'Notification', $message);
        }
    }
}

$user = new AdminUser('Alice', 'alice@example.com', new Address('123 Main St'));
echo $user->name; // Alice
""",
    ),

    # 2. PSR-4 Autoloading & Composer
    (
        "php/psr4-autoloading.md",
        "php",
        ["composer", "pattern"],
        "PSR-4 Autoloading & Composer",
        "Composer autoload configuration, namespaces, and PSR-4 autoloader setup.",
        "pattern",
        """<?php

// composer.json (typical PSR-4 setup)
// {
//   "name": "acme/app",
//   "autoload": {
//     "psr-4": {
//       "Acme\\\\App\\\\": "src/",
//       "Acme\\\\App\\\\Tests\\\\": "tests/"
//     }
//   },
//   "require": {
//     "php": ">=8.1",
//     "guzzlehttp/guzzle": "^7.0"
//   }
// }

// -- src/Models/User.php --
namespace Acme\\App\\Models;

class User {
    public function __construct(
        public readonly int $id,
        public readonly string $name,
    ) {}
}

// -- src/Services/UserService.php --
namespace Acme\\App\\Services;

use Acme\\App\\Models\\User;

class UserService {
    /** @var User[] */
    private array $users = [];

    public function addUser(User $user): void {
        $this->users[$user->id] = $user;
    }

    public function findUser(int $id): ?User {
        return $this->users[$id] ?? null;
    }
}

// -- public/index.php (entry point) --
// require __DIR__ . '/../vendor/autoload.php';
//
// use Acme\\App\\Models\\User;
// use Acme\\App\\Services\\UserService;
//
// $service = new UserService();
// $service->addUser(new User(1, 'Alice'));
// echo $service->findUser(1)?->name;
""",
    ),

    # 3. PDO Database
    (
        "php/pdo-database.md",
        "php",
        ["database", "pattern"],
        "PDO Database",
        "PDO connection, prepared statements, fetch modes, transactions, and error handling.",
        "pattern",
        """<?php

$dsn = 'mysql:host=127.0.0.1;port=3306;dbname=app;charset=utf8mb4';
$username = 'root';
$password = 'secret';
$options = [
    PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    PDO::ATTR_EMULATE_PREPARES   => false,
];

try {
    $pdo = new PDO($dsn, $username, $password, $options);
} catch (PDOException $e) {
    die('Connection failed: ' . $e->getMessage());
}

// Prepared statement (SELECT)
$stmt = $pdo->prepare('SELECT id, name, email FROM users WHERE active = :active');
$stmt->execute([':active' => 1]);
$users = $stmt->fetchAll();

// Prepared statement (INSERT)
$stmt = $pdo->prepare(
    'INSERT INTO users (name, email, active) VALUES (:name, :email, :active)'
);
$stmt->execute([
    ':name'   => 'Alice',
    ':email'  => 'alice@example.com',
    ':active' => 1,
]);
$newId = $pdo->lastInsertId();

// Transactions
try {
    $pdo->beginTransaction();
    $pdo->exec('UPDATE accounts SET balance = balance - 100 WHERE id = 1');
    $pdo->exec('UPDATE accounts SET balance = balance + 100 WHERE id = 2');
    $pdo->commit();
} catch (PDOException $e) {
    $pdo->rollBack();
    error_log('Transfer failed: ' . $e->getMessage());
}

// Named vs positional placeholders
$stmt = $pdo->prepare('SELECT * FROM users WHERE id = ?');
$stmt->execute([42]);
$user = $stmt->fetch();

// Row count
$count = $stmt->rowCount();
""",
    ),

    # 4. Laravel Eloquent
    (
        "php/laravel-eloquent.md",
        "php",
        ["laravel", "pattern"],
        "Laravel Eloquent",
        "Eloquent ORM: model definitions, relationships, scopes, accessors, mutators, eager loading.",
        "pattern",
        """<?php

namespace App\\Models;

use Illuminate\\Database\\Eloquent\\Model;
use Illuminate\\Database\\Eloquent\\Builder;
use Illuminate\\Database\\Eloquent\\Relations\\HasMany;
use Illuminate\\Database\\Eloquent\\Relations\\BelongsTo;

class User extends Model
{
    // Relationships
    public function posts(): HasMany
    {
        return $this->hasMany(Post::class);
    }

    // Accessor
    public function getFullNameAttribute(): string
    {
        return "{$this->first_name} {$this->last_name}";
    }

    // Mutator
    public function setPasswordAttribute(string $value): void
    {
        $this->attributes['password'] = bcrypt($value);
    }

    // Local scope
    public function scopeActive(Builder $query): Builder
    {
        return $query->where('active', true);
    }

    public function scopeVip(Builder $query): Builder
    {
        return $query->where('vip', true);
    }
}

class Post extends Model
{
    protected $fillable = ['title', 'content', 'user_id'];

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    // Global scope example
    protected static function booted(): void
    {
        static::addGlobalScope('published', function (Builder $builder) {
            $builder->where('published', true);
        });
    }
}

// -- Migrations --
// use Illuminate\\Database\\Migrations\\Migration;
// use Illuminate\\Database\\Schema\\Blueprint;
// use Illuminate\\Support\\Facades\\Schema;
//
// return new class extends Migration {
//     public function up(): void {
//         Schema::create('posts', function (Blueprint $table) {
//             $table->id();
//             $table->foreignId('user_id')->constrained()->cascadeOnDelete();
//             $table->string('title');
//             $table->text('content');
//             $table->boolean('published')->default(false);
//             $table->timestamps();
//         });
//     }
// };

// -- Usage --
// $vipUsers = User::active()->vip()->with('posts')->get();
// foreach ($vipUsers as $user) {
//     echo "{$user->full_name}: {$user->posts->count()} posts\\n";
// }
""",
    ),

    # 5. REST API
    (
        "php/rest-api.md",
        "php",
        ["api", "pattern"],
        "REST API",
        "Plain PHP REST API router with JSON responses, CORS, input validation, and error handling.",
        "pattern",
        """<?php

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
""",
    ),

    # 6. Error & Exception Handling
    (
        "php/error-exception-handling.md",
        "php",
        ["error", "pattern"],
        "Error & Exception Handling",
        "Try/catch, set_exception_handler, error_reporting levels, custom exception classes, throwable.",
        "pattern",
        """<?php

// Custom exception class
class ValidationException extends \\RuntimeException
{
    public function __construct(
        string $message = 'Validation failed',
        int $code = 422,
        ?\\Throwable $previous = null,
        public readonly array $errors = [],
    ) {
        parent::__construct($message, $code, $previous);
    }
}

class NotFoundException extends \\RuntimeException
{
    public function __construct(string $resource = 'Resource')
    {
        parent::__construct("{$resource} not found", 404);
    }
}

// Global exception handler
set_exception_handler(function (\\Throwable $e): void {
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
    throw new \\ErrorException($message, 0, $severity, $file, $line);
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
} catch (\\Throwable $e) {
    echo "Unexpected: {$e->getMessage()}";
} finally {
    echo " (done)";
}
""",
    ),

    # 7. String & Array Functions
    (
        "php/string-array-functions.md",
        "php",
        ["utility", "pattern"],
        "String & Array Functions",
        "Essential PHP string and array manipulation: str_replace, preg_match, array_map/filter/reduce.",
        "pattern",
        """<?php

// --- String functions ---
$text = 'Hello, World!';

echo str_replace('World', 'PHP', $text);        // Hello, PHP!
echo str_contains($text, 'World');              // true (PHP 8.0+)
echo str_starts_with($text, 'Hello');           // true (PHP 8.0+)
echo str_ends_with($text, '!');                 // true (PHP 8.0+)

preg_match('/(\\\\w+), (\\\\w+)!/', $text, $matches);
echo $matches[1];  // Hello

$newText = preg_replace('/(\\\\w+)/e', 'strtoupper($1)', $text); // (modern: use preg_replace_callback)
$upper    = preg_replace_callback('/\\\\w+/', fn($m) => strtoupper($m[0]), $text);
echo $upper;  // HELLO, WORLD!

// --- Array functions ---
$numbers = [1, 2, 3, 4, 5];

$doubled = array_map(fn(int $n): int => $n * 2, $numbers);
// [2, 4, 6, 8, 10]

$evens = array_filter($numbers, fn(int $n): bool => $n % 2 === 0);
// [2, 4]

$sum = array_reduce($numbers, fn(int $carry, int $n): int => $carry + $n, 0);
// 15

$keys   = ['a', 'b', 'c'];
$values = [1, 2, 3];
$combined = array_combine($keys, $values);
// ['a' => 1, 'b' => 2, 'c' => 3]

$merged = array_merge(['x' => 1], ['y' => 2]);
// ['x' => 1, 'y' => 2]

$diff = array_diff([1, 2, 3, 4], [2, 4]);
// [1, 3]

$intersect = array_intersect([1, 2, 3], [2, 3, 4]);
// [2, 3]

// Chunk
$chunks = array_chunk(range(1, 10), 3);
// [[1,2,3], [4,5,6], [7,8,9], [10]]

// Column (extract column from multi-dimensional array)
$users = [
    ['id' => 1, 'name' => 'Alice'],
    ['id' => 2, 'name' => 'Bob'],
];
$names = array_column($users, 'name');
// ['Alice', 'Bob']
""",
    ),

    # 8. File Handling
    (
        "php/file-handling.md",
        "php",
        ["io", "pattern"],
        "File Handling",
        "File read/write, CSV parsing, directory iteration via fopen/fgets/fwrite and file_* functions.",
        "pattern",
        """<?php

// --- Basic file reading ---
$content = file_get_contents('/path/to/file.txt');

// Line-by-line (memory efficient)
$handle = fopen('/path/to/large-file.txt', 'r');
if ($handle) {
    while (($line = fgets($handle)) !== false) {
        echo $line;
    }
    fclose($handle);
}

// --- Writing ---
file_put_contents('/path/to/output.txt', 'Hello, World!');

$handle = fopen('/path/to/output.txt', 'w');
fwrite($handle, "Line 1\\n");
fwrite($handle, "Line 2\\n");
fclose($handle);

// Append mode
file_put_contents('/path/to/log.txt', "New entry\\n", FILE_APPEND | LOCK_EX);

// --- CSV handling ---
$handle = fopen('/path/to/data.csv', 'r');
$headers = fgetcsv($handle); // read header row
$rows = [];
while (($row = fgetcsv($handle)) !== false) {
    $rows[] = array_combine($headers, $row);
}
fclose($handle);

// Write CSV
$handle = fopen('/path/to/output.csv', 'w');
fputcsv($handle, ['Name', 'Email', 'Age']);
fputcsv($handle, ['Alice', 'alice@example.com', 30]);
fputcsv($handle, ['Bob', 'bob@example.com', 25]);
fclose($handle);

// --- Directory iteration ---
$dir = '/path/to/dir';
if (is_dir($dir)) {
    $iterator = new DirectoryIterator($dir);
    foreach ($iterator as $fileinfo) {
        if (!$fileinfo->isDot()) {
            echo $fileinfo->getFilename() . ' - '
                 . ($fileinfo->isDir() ? 'dir' : 'file') . "\\n";
        }
    }
}

// Recursive directory iterator
$rit = new RecursiveIteratorIterator(
    new RecursiveDirectoryIterator($dir, RecursiveDirectoryIterator::SKIP_DOTS)
);
foreach ($rit as $file) {
    if ($file->isFile() && $file->getExtension() === 'php') {
        echo $file->getPathname() . "\\n";
    }
}
""",
    ),

    # 9. Sessions & Cookies
    (
        "php/sessions-cookies.md",
        "php",
        ["auth", "pattern"],
        "Sessions & Cookies",
        "Session management, cookie handling, flash messages, and CSRF token pattern.",
        "pattern",
        """<?php

// --- Session Configuration ---
ini_set('session.use_strict_mode', 1);
ini_set('session.use_only_cookies', 1);
ini_set('session.cookie_httponly', 1);
ini_set('session.cookie_samesite', 'Lax');
session_set_cookie_params([
    'lifetime' => 7200,
    'path'     => '/',
    'domain'   => '',
    'secure'   => true,
    'httponly' => true,
    'samesite' => 'Lax',
]);

session_start();

// --- Flash messages ---
function setFlash(string $type, string $message): void {
    $_SESSION['_flash'][] = ['type' => $type, 'message' => $message];
}

function getFlashes(): array {
    $flashes = $_SESSION['_flash'] ?? [];
    unset($_SESSION['_flash']);
    return $flashes;
}

// --- CSRF Token ---
if (empty($_SESSION['_csrf_token'])) {
    $_SESSION['_csrf_token'] = bin2hex(random_bytes(32));
}

function csrfToken(): string {
    return $_SESSION['_csrf_token'];
}

function csrfField(): string {
    return '<input type="hidden" name="_csrf_token" value="' . csrfToken() . '">';
}

function verifyCsrf(?string $token): bool {
    return hash_equals($_SESSION['_csrf_token'] ?? '', $token ?? '');
}

// --- Cookie handling ---
setcookie('preferences', json_encode(['theme' => 'dark']), [
    'expires'  => time() + 86400 * 30,
    'path'     => '/',
    'secure'   => true,
    'httponly' => true,
    'samesite' => 'Lax',
]);

$prefs = json_decode($_COOKIE['preferences'] ?? '{}', true);

// --- Login example ---
// if (password_verify($password, $user['password_hash'])) {
//     session_regenerate_id(true);
//     $_SESSION['user_id'] = $user['id'];
//     setFlash('success', 'Welcome back!');
//     header('Location: /dashboard');
//     exit;
// }
""",
    ),

    # 10. Middleware Pattern
    (
        "php/middleware-pattern.md",
        "php",
        ["architecture", "pattern"],
        "Middleware Pattern",
        "PSR-15 style middleware: request handler chain, before/after, logging and auth middleware.",
        "pattern",
        """<?php

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
""",
    ),

    # 11. DateTime & Carbon
    (
        "php/datetime-carbon.md",
        "php",
        ["date", "pattern"],
        "DateTime & Carbon",
        "DateTime and DateTimeImmutable classes, Carbon library usage: diff, format, timezone handling.",
        "pattern",
        """<?php

// --- Built-in DateTime ---
$now = new DateTime();
echo $now->format('Y-m-d H:i:s');          // 2026-06-05 12:00:00

$immutable = new DateTimeImmutable();
$future = $immutable->modify('+7 days');    // Returns new object (immutable)
echo $future->format('Y-m-d');

// Timezone handling
$tz = new DateTimeZone('America/New_York');
$dt = new DateTime('now', $tz);
echo $dt->format('Y-m-d H:i:s T');

// Convert timezone
$dt->setTimezone(new DateTimeZone('UTC'));
echo $dt->format('Y-m-d H:i:s');

// Date intervals
$start = new DateTime('2026-01-01');
$end   = new DateTime('2026-12-31');
$diff  = $start->diff($end);
echo $diff->days;      // 364
echo $diff->format('%y years %m months');

// DatePeriod iteration
$period = new DatePeriod(
    new DateTime('2026-01-01'),
    new DateInterval('P1M'),
    new DateTime('2026-12-31'),
);
foreach ($period as $date) {
    echo $date->format('Y-m-d') . "\\n";
}

// --- Carbon (if installed via Composer) ---
// use Carbon\\Carbon;
// use Carbon\\CarbonImmutable;
//
// Carbon::setLocale('fr');
// echo Carbon::now()->addDays(5)->diffForHumans();       // dans 5 jours
// echo Carbon::now()->subWeek()->diffForHumans();        // il y a 1 semaine
//
// $created = Carbon::parse('2026-01-15');
// echo $created->diffInDays();                           // days since
// echo $created->startOfMonth()->format('Y-m-d');        // 2026-01-01
// echo $created->endOfMonth()->format('Y-m-d');          // 2026-01-31
""",
    ),

    # 12. Dependency Injection
    (
        "php/dependency-injection.md",
        "php",
        ["architecture", "pattern"],
        "Dependency Injection",
        "PSR-11 container pattern, constructor injection, service providers, and autowiring.",
        "pattern",
        """<?php

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
        echo "[LOG] {$msg}\\n";
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
""",
    ),

    # 13. Testing (PHPUnit)
    (
        "php/testing-phpunit.md",
        "php",
        ["testing", "pattern"],
        "Testing (PHPUnit)",
        "PHPUnit test cases: setUp, @test annotations, assertions, mocks, data providers.",
        "pattern",
        """<?php

use PHPUnit\\Framework\\TestCase;
// use Mockery;
// use Mockery\\Adapter\\Phpunit\\MockeryPHPUnitIntegration;

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
""",
    ),

    # 14. Security
    (
        "php/security.md",
        "php",
        ["security", "pattern"],
        "Security",
        "Password hashing/verification, XSS prevention, input filtering, SQL injection prevention, CSRF.",
        "pattern",
        """<?php

// --- Password Hashing ---
$password = 's3cret!';
$hash = password_hash($password, PASSWORD_BCRYPT, ['cost' => 12]);
// Store $hash in database

if (password_verify($password, $hash)) {
    echo 'Password is valid!';
}

// Check if rehashing is needed
if (password_needs_rehash($hash, PASSWORD_BCRYPT, ['cost' => 13])) {
    $newHash = password_hash($password, PASSWORD_BCRYPT, ['cost' => 13]);
    // Update stored hash
}

// --- XSS Prevention ---
$userInput = '<script>alert("xss")</script>';
$safe = htmlspecialchars($userInput, ENT_QUOTES | ENT_HTML5, 'UTF-8');
echo $safe;
// &lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;

// --- Input Filtering ---
$email = filter_input(INPUT_POST, 'email', FILTER_VALIDATE_EMAIL);
$age   = filter_input(INPUT_POST, 'age', FILTER_VALIDATE_INT, [
    'options' => ['min_range' => 1, 'max_range' => 150],
]);
$url   = filter_input(INPUT_GET, 'redirect', FILTER_VALIDATE_URL);

// Sanitization
$name      = filter_var($rawName, FILTER_SANITIZE_STRING);
$cleanHtml = strip_tags($rawHtml, '<p><a><br>');

// --- SQL Injection Prevention (with PDO prepared statements) ---
$stmt = $pdo->prepare('SELECT * FROM users WHERE email = :email AND active = :active');
$stmt->execute([':email' => $email, ':active' => 1]);

// Never: $pdo->query("SELECT * FROM users WHERE id = {$_GET['id']}");

// --- CSRF Prevention (token pattern) ---
session_start();
if (empty($_SESSION['_token'])) {
    $_SESSION['_token'] = bin2hex(random_bytes(32));
}

function csrf_token(): string {
    return $_SESSION['_token'];
}

function verify_token(string $token): bool {
    return hash_equals($_SESSION['_token'], $token);
}

// In form: <input type="hidden" name="_token" value="<?= csrf_token() ?>">
// On submit: if (!verify_token($_POST['_token'] ?? '')) { die('CSRF detected'); }

// --- Output encoding context matters ---
// HTML: htmlspecialchars($data, ENT_QUOTES, 'UTF-8')
// JS: json_encode($data)
// URL: rawurlencode($data)
// CSS: not recommended to embed user input
""",
    ),

    # 15. CLI Scripts
    (
        "php/cli-scripts.md",
        "php",
        ["cli", "pattern"],
        "CLI Scripts",
        "PHP CLI: argv/getopt, php://input, Symfony Console commands, progress bars.",
        "pattern",
        """<?php

// --- Basic CLI: argv and exit codes ---
// Run: php script.php --name=Alice --verbose
if (PHP_SAPI !== 'cli') {
    exit(1);
}

$options = getopt('', ['name::', 'verbose']);
$name    = $options['name'] ?? 'World';
$verbose = isset($options['verbose']);

echo "Hello, {$name}!\\n";
if ($verbose) {
    echo "Verbose mode enabled\\n";
    echo "Args: " . json_encode($argv) . "\\n";
}

// --- Reading from stdin ---
$stdin = file_get_contents('php://stdin');
// echo strtoupper($stdin);

// --- Progress bar (pure PHP) ---
function progressBar(int $done, int $total, int $width = 50): void {
    $percent = ($total > 0) ? round($done / $total * 100) : 0;
    $fill    = round($width * $done / $total);
    $bar     = str_repeat('=', $fill) . str_repeat(' ', $width - $fill);
    echo "\\r[" . $bar . "] {$percent}% ({$done}/{$total})";
    if ($done === $total) {
        echo "\\n";
    }
}

$total = 50;
for ($i = 1; $i <= $total; $i++) {
    usleep(50000); // simulate work
    progressBar($i, $total);
}

// --- Symfony Console (requires symfony/console) ---
// use Symfony\\Component\\Console\\Command\\Command;
// use Symfony\\Component\\Console\\Input\\InputInterface;
// use Symfony\\Component\\Console\\Output\\OutputInterface;
// use Symfony\\Component\\Console\\Input\\InputOption;
// use Symfony\\Component\\Console\\Application;
//
// class GreetCommand extends Command
// {
//     protected function configure(): void
//     {
//         $this->setName('app:greet')
//              ->addOption('name', null, InputOption::VALUE_REQUIRED, 'Who to greet')
//              ->addOption('yell', null, InputOption::VALUE_NONE, 'Yell the greeting');
//     }
//
//     protected function execute(InputInterface $input, OutputInterface $output): int
//     {
//         $name = $input->getOption('name') ?? 'World';
//         $text = "Hello, {$name}!";
//         if ($input->getOption('yell')) {
//             $text = strtoupper($text);
//         }
//         $output->writeln($text);
//         return Command::SUCCESS;
//     }
// }
//
// $app = new Application();
// $app->add(new GreetCommand());
// $app->run();
""",
    ),

    # ============================================================
    # RUBY SNIPPETS (1-15)
    # ============================================================
    # 1. Classes & Modules
    (
        "ruby/classes-modules.md",
        "ruby",
        ["oop", "pattern"],
        "Classes & Modules",
        "Ruby classes, modules, mixins (include/extend/prepend), attr_accessor, inheritance, super.",
        "pattern",
        """class Animal
  attr_accessor :name

  def initialize(name)
    @name = name
  end

  def speak
    raise NotImplementedError, 'subclasses must implement speak'
  end
end

module Walkable
  def walk
    "#{name} is walking"
  end
end

module Swimmable
  def swim
    "#{name} is swimming"
  end
end

class Dog < Animal
  include Walkable
  include Swimmable

  def speak
    'Woof!'
  end
end

class Cat < Animal
  include Walkable

  def speak
    'Meow!'
  end

  # Prepend example (prepended modules override class methods)
end

module Logger
  def speak
    "[LOG] #{super}"
  end
end

class LoggedCat < Cat
  prepend Logger
end

# Extend adds module methods as class methods
module ClassMethods
  def species
    'Mammal'
  end
end

class Bird < Animal
  extend ClassMethods
end

dog = Dog.new('Rex')
puts dog.speak   # Woof!
puts dog.walk    # Rex is walking
puts dog.swim    # Rex is swimming

cat = LoggedCat.new('Luna')
puts cat.speak   # [LOG] Meow!

puts Bird.species # Mammal
""",
    ),

    # 2. Blocks, Procs & Lambdas
    (
        "ruby/blocks-procs-lambdas.md",
        "ruby",
        ["functional", "pattern"],
        "Blocks, Procs & Lambdas",
        "Blocks (yield, block_given?), Proc.new, lambda, &block conversion, Symbol#to_proc.",
        "pattern",
        """# --- Blocks ---
def timer
  start = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  yield if block_given?
  finish = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  "Elapsed: #{finish - start}s"
end

result = timer { sleep(0.1) }
puts result  # Elapsed: ~0.1s

# Block with arguments
def each_item(array)
  array.each_with_index { |item, idx| yield(item, idx) }
end

each_item(%w[a b c]) do |item, idx|
  puts "#{idx}: #{item}"
end

# --- Proc ---
# Procs don't enforce arity (unlike lambdas)
double = proc { |x| x * 2 }
puts double.call(5)         # 10
puts double.call(5, 10)     # 10 (extra arg ignored)

# --- Lambda ---
# Lambdas DO enforce arity
square = ->(x) { x * x }
puts square.call(4)         # 16
# square.call(1, 2) would raise ArgumentError

# Lambda with multiple args
add = ->(a, b) { a + b }
puts add.call(3, 4)         # 7

# --- &block conversion ---
def method_with_block(&block)
  block.call('from method')
end

method_with_block { |msg| puts msg }

# Passing a proc as a block
my_proc = proc { |n| n ** 2 }
[1, 2, 3].map(&my_proc)    # [1, 4, 9]

# Symbol#to_proc
puts %w[alice bob charlie].map(&:capitalize).join(', ')
# Alice, Bob, Charlie

[10, 20, 30].map(&:to_s)   # ['10', '20', '30']

# --- Proc vs Lambda differences ---
def proc_return
  p = proc { return 'proc return' }
  p.call
  'never reached'
end

def lambda_return
  l = -> { return 'lambda return' }
  l.call
  'after lambda'
end

puts proc_return   # proc return (return exits the enclosing method)
puts lambda_return # after lambda (return just exits the lambda)
""",
    ),

    # 3. Enumerable & Arrays
    (
        "ruby/enumerable-arrays.md",
        "ruby",
        ["collections", "pattern"],
        "Enumerable & Arrays",
        "Ruby Enumerable module: map/select/reduce, each_with_object, group_by, lazy enumerators.",
        "pattern",
        """# --- Core Enumerable methods ---
numbers = [1, 2, 3, 4, 5, 6]

doubled = numbers.map { |n| n * 2 }
# [2, 4, 6, 8, 10, 12]

evens = numbers.select(&:even?)
# [2, 4, 6]

odds = numbers.reject(&:even?)
# [1, 3, 5]

sum = numbers.reduce(0) { |acc, n| acc + n }
# 21
sum = numbers.sum          # 21 (Ruby 2.4+)

product = numbers.reduce(1, :*)
# 720

# --- each_with_object ---
grouped = numbers.each_with_object({}) do |n, hash|
  hash[n.even? ? 'even' : 'odd'] ||= []
  hash[n.even? ? 'even' : 'odd'] << n
end
# {'odd' => [1, 3, 5], 'even' => [2, 4, 6]}

# --- group_by ---
words = %w[apple ant bear cat dog elephant]
by_first_letter = words.group_by { |w| w[0] }
# {'a' => ['apple', 'ant'], 'b' => ['bear'], 'c' => ['cat'], 'd' => ['dog'], 'e' => ['elephant']}

# --- sort_by ---
sorted = words.sort_by(&:length)
# ['ant', 'cat', 'dog', 'bear', 'apple', 'elephant']

# --- chunk ---
chunks = [1, 1, 2, 2, 2, 3, 1, 1].chunk(&:itself).to_a
# [[1, [1, 1]], [2, [2, 2, 2]], [3, [3]], [1, [1, 1]]]

# --- Lazy enumerators ---
lazy = (1..Float::INFINITY).lazy
  .map { |n| n * n }
  .select(&:even?)
  .first(5)
# [4, 16, 36, 64, 100]

# --- Custom Enumerable ---
class Fibonacci
  include Enumerable

  def each
    a, b = 0, 1
    loop do
      yield a
      a, b = b, a + b
    end
  end
end

Fibonacci.new.first(10)  # [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
""",
    ),

    # 4. Ruby on Rails API
    (
        "ruby/rails-api.md",
        "ruby",
        ["rails", "pattern"],
        "Ruby on Rails API",
        "Rails ActiveRecord, associations, routes, controllers, and serializers for API development.",
        "pattern",
        """# == Models ==
# app/models/user.rb
class User < ApplicationRecord
  has_many :posts, dependent: :destroy

  validates :email, presence: true, uniqueness: true
  validates :name, presence: true

  scope :active, -> { where(active: true) }
  scope :recent, -> { order(created_at: :desc) }
end

# app/models/post.rb
class Post < ApplicationRecord
  belongs_to :user, counter_cache: true

  validates :title, presence: true
  validates :body, presence: true

  scope :published, -> { where(published: true) }
  scope :drafts, -> { where(published: false) }
end

# == Migrations ==
# class CreateUsers < ActiveRecord::Migration[7.1]
#   def change
#     create_table :users do |t|
#       t.string :name, null: false
#       t.string :email, null: false
#       t.boolean :active, default: true
#       t.timestamps
#     end
#     add_index :users, :email, unique: true
#   end
# end

# == Routes ==
# config/routes.rb
# Rails.application.routes.draw do
#   namespace :api do
#     namespace :v1 do
#       resources :users, only: %i[index show create update destroy] do
#         resources :posts, only: %i[index create]
#       end
#     end
#   end
# end

# == Controller ==
# app/controllers/api/v1/users_controller.rb
module Api
  module V1
    class UsersController < ApplicationController
      before_action :set_user, only: %i[show update destroy]

      def index
        users = User.active.recent
        render json: users, each_serializer: UserSerializer
      end

      def show
        render json: @user, serializer: UserSerializer
      end

      def create
        user = User.new(user_params)
        if user.save
          render json: user, serializer: UserSerializer, status: :created
        else
          render json: { errors: user.errors.full_messages }, status: :unprocessable_entity
        end
      end

      private

      def set_user
        @user = User.find(params[:id])
      end

      def user_params
        params.require(:user).permit(:name, :email)
      end
    end
  end
end

# == Serializer (using ActiveModelSerializers or jsonapi-serializer) ==
# class UserSerializer
#   include JSONAPI::Serializer
#
#   attributes :name, :email, :active
#   has_many :posts
# end
""",
    ),

    # 5. Error Handling
    (
        "ruby/error-handling.md",
        "ruby",
        ["error", "pattern"],
        "Error Handling",
        "Ruby exception handling: begin/rescue/ensure/else, custom exceptions, retry, StandardError.",
        "pattern",
        """# --- Basic error handling ---
begin
  result = 10 / 0
rescue ZeroDivisionError => e
  puts "Caught: #{e.message}"
rescue TypeError => e
  puts "Type error: #{e.message}"
else
  puts "No error occurred, result is #{result}"
ensure
  puts 'This always runs (cleanup)'
end

# --- Custom exceptions ---
class AppError < StandardError; end
class ValidationError < AppError; end
class NotFoundError < AppError; end

def find_user(id)
  raise NotFoundError, "User #{id} not found" if id.nil? || id <= 0
  { id: id, name: 'Alice' }
end

begin
  find_user(nil)
rescue ValidationError => e
  puts "Validation: #{e.message}"
rescue NotFoundError => e
  puts "Not found: #{e.message}"
rescue AppError => e
  puts "App error: #{e.message}"
end

# --- Retry ---
attempts = 0
begin
  attempts += 1
  puts "Attempt #{attempts}"
  raise 'temporary failure' if attempts < 3
rescue StandardError => e
  puts "Failed: #{e.message}"
  retry if attempts < 3
end

# --- Ensure with early return ---
def risky_operation
  file = File.open('/tmp/test.txt', 'w')
  return 'done'  # ensure still runs
ensure
  file&.close
  puts 'File closed'
end

puts risky_operation

# --- Rescue inline ---
value = risky_method rescue 'default'
# (catches any StandardError)

# --- Exception hierarchy ---
# StandardError
#   +-- RuntimeError
#   +-- ArgumentError
#   +-- NameError
#   +-- NoMethodError
#   +-- TypeError
#   +-- ZeroDivisionError
#
# Exception (top-level, rarely rescue directly)
#   +-- SystemExit
#   +-- SignalException
#   +-- NoMemoryError
""",
    ),

    # 6. File I/O
    (
        "ruby/file-io.md",
        "ruby",
        ["io", "pattern"],
        "File I/O",
        "File read/write, Dir.glob, CSV parsing, Pathname, Tempfile, IO.popen.",
        "pattern",
        """require 'csv'
require 'pathname'
require 'tempfile'
require 'fileutils'

# --- Basic file reading ---
content = File.read('/path/to/file.txt')
lines   = File.readlines('/path/to/file.txt')

# Line-by-line (memory efficient)
File.foreach('/path/to/large-file.txt') do |line|
  puts line
end

# --- File writing ---
File.write('/path/to/output.txt', 'Hello, World!')

File.open('/path/to/output.txt', 'w') do |f|
  f.puts 'Line 1'
  f.puts 'Line 2'
end

# Append mode
File.open('/path/to/log.txt', 'a') do |f|
  f.puts "New entry at #{Time.now}"
end

# --- CSV ---
CSV.foreach('/path/to/data.csv', headers: true) do |row|
  puts "#{row['Name']}: #{row['Email']}"
end

CSV.open('/path/to/output.csv', 'w') do |csv|
  csv << %w[Name Email Age]
  csv << %w[Alice alice@example.com 30]
  csv << %w[Bob bob@example.com 25]
end

# --- Dir.glob ---
Dir.glob('src/**/*.rb').each { |f| puts f }
Dir.glob(['*.txt', '*.md'])  # multiple patterns
Dir.glob('**/*').select { |f| File.file?(f) }

# --- Pathname ---
path = Pathname.new('/path/to/file.txt')
puts path.basename      # file.txt
puts path.dirname       # /path/to
puts path.extname       # .txt
puts path.join('subdir', 'other.txt')

# --- Tempfile ---
Tempfile.create(%w[prefix .csv]) do |f|
  f.puts 'data'
  f.path  # => /tmp/prefix20260101-1234-abc.csv
end  # auto-deleted

# --- IO.popen ---
IO.popen('ls -la', &:read)  # reads command output

# --- FileUtils ---
FileUtils.mkdir_p('/path/to/nested/dir')
FileUtils.cp('/source.txt', '/dest.txt')
FileUtils.mv('/old.txt', '/new.txt')
FileUtils.rm_rf('/path/to/delete')
""",
    ),

    # 7. Gems & Bundler
    (
        "ruby/gems-bundler.md",
        "ruby",
        ["dependencies", "pattern"],
        "Gems & Bundler",
        "Gemfile, gemspec, bundler setup, require, version constraints, Rake tasks.",
        "pattern",
        """# == Gemfile ==
# source 'https://rubygems.org'
#
# ruby '>= 3.1'
#
# gem 'rails', '~> 7.1'
# gem 'pg', '~> 1.5'
# gem 'puma', '>= 6.0'
# gem 'bootsnap', require: false
#
# group :development, :test do
#   gem 'rspec-rails', '~> 6.0'
#   gem 'factory_bot_rails'
#   gem 'rubocop', require: false
# end
#
# group :development do
#   gem 'better_errors'
#   gem 'binding_of_caller'
# end
#
# group :test do
#   gem 'shoulda-matchers'
#   gem 'database_cleaner-active_record'
# end
#
# gem 'rack-cors', '~> 2.0'

# == Bundler setup ==
# require 'bundler/setup'
# Bundler.require(:default, :development)

# == .gemspec (for gem development) ==
# Gem::Specification.new do |spec|
#   spec.name          = 'my_gem'
#   spec.version       = '0.1.0'
#   spec.authors       = ['Alice']
#   spec.email         = ['alice@example.com']
#   spec.summary       = 'A summary'
#   spec.description   = 'A longer description'
#   spec.license       = 'MIT'
#
#   spec.required_ruby_version = '>= 3.1'
#
#   spec.files = Dir['lib/**/*.rb'] + %w[README.md LICENSE]
#
#   spec.add_dependency 'faraday', '~> 2.0'
#   spec.add_development_dependency 'rspec', '~> 3.12'
# end

# == Version constraints ==
# gem 'nokogiri', '>= 1.14', '< 2.0'
# gem 'sidekiq', '~> 7.0'    # >= 7.0, < 8.0
# gem 'redis',  '~> 5.0.0'   # >= 5.0.0, < 5.1.0

# == Rake tasks ==
# require 'bundler/gem_tasks'
# require 'rspec/core/rake_task'
#
# RSpec::Core::RakeTask.new(:spec)
# task default: :spec

# == Using bundler inline (without Gemfile) ==
# require 'bundler/inline'
#
# gemfile do
#   source 'https://rubygems.org'
#   gem 'json'
#   gem 'httparty'
# end
""",
    ),

    # 8. Metaprogramming
    (
        "ruby/metaprogramming.md",
        "ruby",
        ["meta", "pattern"],
        "Metaprogramming",
        "method_missing, define_method, class_eval, instance_eval, send, respond_to_missing?.",
        "pattern",
        """# --- method_missing ---
class DynamicProxy
  def initialize(target)
    @target = target
  end

  def method_missing(name, *args, &block)
    if @target.respond_to?(name)
      @target.send(name, *args, &block)
    else
      super  # raise NoMethodError
    end
  end

  def respond_to_missing?(name, include_private = false)
    @target.respond_to?(name, include_private) || super
  end
end

proxy = DynamicProxy.new([1, 2, 3])
puts proxy.length  # 3
puts proxy.respond_to?(:length)  # true

# --- define_method ---
class AttributeBuilder
  %i[name email age].each do |attr|
    define_method(attr) do
      instance_variable_get("@#{attr}")
    end

    define_method("#{attr}=") do |value|
      instance_variable_set("@#{attr}", value)
    end
  end
end

obj = AttributeBuilder.new
obj.name = 'Alice'
puts obj.name  # Alice

# --- class_eval / instance_eval ---
class Greeter; end

Greeter.class_eval do
  def hello
    'Hello!'
  end
end

puts Greeter.new.hello  # Hello!

# instance_eval opens the singleton class
obj = 'hello'
obj.instance_eval do
  def shout
    upcase + '!'
  end
end
puts obj.shout  # HELLO!

# --- send (dynamic invocation) ---
method_name = :upcase
puts 'hello'.send(method_name)  # HELLO

# --- Define class methods dynamically ---
class Config
  class << self
    def attr_config(*names)
      names.each do |name|
        define_method(name) do
          instance_variable_get("@#{name}")
        end

        define_method("#{name}=") do |value|
          instance_variable_set("@#{name}", value)
        end
      end
    end
  end

  attr_config :app_name, :version, :debug
end

Config.new.tap do |c|
  c.app_name = 'MyApp'
  c.version = '2.0'
  puts c.app_name  # MyApp
end
""",
    ),

    # 9. Strings & Regex
    (
        "ruby/strings-regex.md",
        "ruby",
        ["utility", "pattern"],
        "Strings & Regex",
        "String manipulation: gsub, scan, match, split, %w/%i literals, interpolation, squish, humanize.",
        "pattern",
        """# --- String literals ---
name = 'Alice'
double_quote = "Hello, #{name}!"         # interpolation
single_quote = 'Hello, #{name}!'         # literal

# %w / %i literals
words = %w[apple banana cherry]           # ['apple', 'banana', 'cherry']
syms  = %i[red green blue]               # [:red, :green, :blue]
multi = <<~TEXT
  Multiline
  string
TEXT

# --- gsub (global substitution) ---
text = 'Hello, World!'
puts text.gsub('World', 'Ruby')          # Hello, Ruby!
puts text.gsub(/[aeiou]/i, '*')          # H*ll*, W*rld!
puts text.gsub(/[A-Z]/) { |c| "[#{c}]" } # [H]ello, [W]orld!

# --- scan ---
numbers = 'abc123def456ghi789'
puts numbers.scan(/\\\\d+/).inspect        # ['123', '456', '789']
pairs   = 'a=1,b=2,c=3'.scan(/(\\\\w)=(\\\\d)/)
# [['a', '1'], ['b', '2'], ['c', '3']]

# --- match ---
match = 'user@example.com'.match(/\\\\A(\\\\w+)@(.+)\\\\z/)
if match
  puts match[1]  # user
  puts match[2]  # example.com
end

# Named captures
m = '2026-06-05'.match(/(?<year>\\\\d{4})-(?<month>\\\\d{2})-(?<day>\\\\d{2})/)
puts m[:year]   # 2026

# --- split ---
csv = 'a,b,c,d'
puts csv.split(',').inspect               # ['a', 'b', 'c', 'd']
sentence = 'Hello   World!'
puts sentence.split.inspect                # ['Hello', 'World!']
puts sentence.split(/\\\\s+/, 2).inspect   # ['Hello', 'World!']

# --- ActiveSupport-style methods (require 'active_support/core_ext') ---
# require 'active_support/core_ext'
# puts 'hello_world'.humanize  # 'Hello world'
# puts '  lots   of   space '.squish  # 'lots of space'
# puts 'hello'.titleize  # 'Hello'
# puts 'User'.pluralize  # 'Users'

# --- Other useful string methods ---
'hello'.capitalize   # 'Hello'
'HELLO'.downcase     # 'hello'
'hello'.upcase       # 'HELLO'
'  hi  '.strip       # 'hi'
'hello'.reverse      # 'olleh'
'hello'.ljust(10)    # 'hello     '
'hello'.rjust(10)    # '     hello'
'42'.to_i            # 42
'3.14'.to_f          # 3.14
""",
    ),

    # 10. Testing with RSpec
    (
        "ruby/testing-rspec.md",
        "ruby",
        ["testing", "pattern"],
        "Testing with RSpec",
        "RSpec: describe/it/expect, let/subject, context, mocks/doubles, shared_examples.",
        "pattern",
        """# == Basic RSpec structure ==
# spec/user_spec.rb
# require 'rails_helper' (or 'spec_helper')

# RSpec.describe User do
#   describe 'validations' do
#     subject { User.new(name: 'Alice', email: 'alice@example.com') }
#
#     it { is_expected.to be_valid }
#
#     it 'is invalid without an email' do
#       subject.email = nil
#       expect(subject).not_to be_valid
#       expect(subject.errors[:email]).to include("can't be blank")
#     end
#   end
#
#   describe '#full_name' do
#     let(:user) { User.new(first_name: 'Alice', last_name: 'Smith') }
#
#     it 'joins first and last name' do
#       expect(user.full_name).to eq 'Alice Smith'
#     end
#   end
# end

# --- let / subject ---
RSpec.describe Array do
  subject(:array) { [3, 1, 2] }

  describe '#sort' do
    it 'returns a sorted array' do
      expect(array.sort).to eq [1, 2, 3]
    end

    it 'does not modify the original' do
      expect { array.sort }.not_to change(array, :itself)
    end
  end
end

# --- context ---
RSpec.describe 'String' do
  context 'when empty' do
    it 'is empty' do
      expect(''.empty?).to be true
    end
  end

  context 'when not empty' do
    it 'is not empty' do
      expect('hello'.empty?).to be false
    end
  end
end

# --- Mocks / Doubles ---
RSpec.describe 'Mocks' do
  it 'uses a test double' do
    notifier = double('Notifier')
    expect(notifier).to receive(:send).
      with('Hello').
      and_return(true)

    service = NotificationService.new(notifier)
    service.notify('Hello')
  end

  it 'stubs a method' do
    user = instance_double(User, name: 'Alice', email: 'alice@test.com')
    allow(user).to receive(:admin?).and_return(true)
    expect(user.admin?).to be true
  end
end

# --- shared_examples ---
RSpec.shared_examples 'a countable' do
  it 'responds to count' do
    expect(subject).to respond_to(:count)
  end

  it 'has a non-negative count' do
    expect(subject.count).to be >= 0
  end
end

# RSpec.describe Array do
#   it_behaves_like 'a countable'
# end
#
# RSpec.describe Hash do
#   it_behaves_like 'a countable'
# end

# --- Pending / Skip ---
# RSpec.describe 'WIP' do
#   xit 'is skipped' do
#     expect(true).to eq false
#   end
#
#   it 'is pending' do
#     pending 'not implemented yet'
#     expect(some_complex_thing).to be_done
#   end
# end
""",
    ),

    # 11. Concurrency
    (
        "ruby/concurrency.md",
        "ruby",
        ["concurrency", "pattern"],
        "Concurrency",
        "Thread, Mutex, Queue, Fiber, Concurrent::Future from concurrent-ruby gem.",
        "pattern",
        """require 'concurrent'  # gem 'concurrent-ruby'

# --- Thread basics ---
threads = []
results = []

mutex = Mutex.new

5.times do |i|
  threads << Thread.new(i) do |n|
    sleep(rand * 0.1)
    mutex.synchronize do
      results << n * 2
    end
  end
end

threads.each(&:join)
puts results.sort.inspect  # [0, 2, 4, 6, 8]

# --- Thread pool via Queue ---
queue = Queue.new
workers = 4.times.map do
  Thread.new do
    until (item = queue.pop(true) rescue nil).nil?
      sleep(0.05)
      puts "Processed #{item}"
    end
  end
end

(1..20).each { |i| queue << i }
queue.close
workers.each(&:join)

# --- Fiber (cooperative concurrency) ---
fiber = Fiber.new do
  puts 'Fiber: step 1'
  Fiber.yield
  puts 'Fiber: step 2'
end

puts 'Main: before resume'
fiber.resume
puts 'Main: between resumes'
fiber.resume
puts 'Main: done'

# --- Concurrent::Future (from concurrent-ruby) ---
futures = 5.times.map do |i|
  Concurrent::Future.execute do
    sleep(rand * 0.2)
    i ** 2
  end
end

# Block until all complete
values = futures.map(&:value!)
puts values.sort.inspect  # [0, 1, 4, 9, 16]

# --- Concurrent::Promise chain ---
promise = Concurrent::Promise.new { 42 }
  .then { |v| v * 2 }
  .then { |v| "Answer: #{v}" }
  .execute

puts promise.value!  # Answer: 84

# --- Actor-like pattern with concurrent-ruby ---
class Counter
  def initialize
    @count = 0
    @mutex = Mutex.new
  end

  def increment
    @mutex.synchronize { @count += 1 }
  end

  def value
    @mutex.synchronize { @count }
  end
end

counter = Counter.new
10.times.map { Thread.new { 100.times { counter.increment } } }.each(&:join)
puts counter.value  # 1000
""",
    ),

    # 12. Sinatra Web App
    (
        "ruby/sinatra-web-app.md",
        "ruby",
        ["web", "pattern"],
        "Sinatra Web App",
        "Sinatra::Base application: routing, params, ERB templates, before/after filters, sessions.",
        "pattern",
        """require 'sinatra/base'
require 'erb'
require 'json'

# Modular Sinatra app (Sinatra::Base)
class MyApp < Sinatra::Base
  # --- Configuration ---
  configure do
    set :sessions, true
    set :session_secret, 'your-secret-here'
    set :show_exceptions, false
    set :views, File.join(__dir__, 'views')
    set :public_folder, File.join(__dir__, 'public')
  end

  # --- Before/After filters ---
  before do
    content_type :html
    @start_time = Time.now
  end

  after do
    elapsed = Time.now - @start_time
    logger.info "Request took #{elapsed}s"
  end

  # --- Routes ---

  get '/' do
    erb :index, locals: { title: 'Home', message: 'Hello, Sinatra!' }
  end

  get '/api/status' do
    content_type :json
    { status: 'ok', time: Time.now.iso8601 }.to_json
  end

  # URL params
  get '/users/:id' do
    "User ##{params[:id]}"
  end

  # Query params
  get '/search' do
    q = params[:q]
    "Search results for: #{q}"
  end

  # Form POST
  post '/users' do
    name = params[:name]
    email = params[:email]
    "Created user #{name} (#{email})"
  end

  # JSON body
  post '/api/users' do
    content_type :json
    data = JSON.parse(request.body.read)
    { id: rand(100), name: data['name'] }.to_json
  end

  # --- Sessions ---
  get '/login' do
    session[:user_id] = params[:id]
    "Logged in as user #{session[:user_id]}"
  end

  get '/logout' do
    session.clear
    'Logged out'
  end

  # --- Error handling ---
  error 404 do
    'Not found'
  end

  error 500 do
    'Internal server error'
  end

  # --- Run if executed directly ---
  run! if app_file == $0
end

# == views/index.erb ==
# <!DOCTYPE html>
# <html>
# <head><title><%= title %></title></head>
# <body>
#   <h1><%= message %></h1>
# </body>
# </html>
""",
    ),

    # 13. Symbols & Hashes
    (
        "ruby/symbols-hashes.md",
        "ruby",
        ["collections", "pattern"],
        "Symbols & Hashes",
        "Symbol vs string, Hash#fetch/merge/transform_keys/dig, keyword arguments, ** splat.",
        "pattern",
        """# --- Symbols vs Strings ---
:symbol        # immutable, interned, used as identifiers
'string'       # mutable, different object each time

# Key differences:
puts :hello.object_id == :hello.object_id  # true (same object)
puts 'hello'.object_id == 'hello'.object_id  # false (different objects)

# Common use: hash keys
user = { name: 'Alice', age: 30, admin: true }
user[:name]  # 'Alice'

# --- Hash#fetch (safe key access) ---
config = { host: 'localhost', port: 3000 }

puts config.fetch(:host)                    # 'localhost'
puts config.fetch(:missing, 'default')      # 'default'
puts config.fetch(:missing) { |key| "key #{key} not found" }
# config.fetch(:missing)                    # KeyError!

# --- Hash#merge ---
defaults = { host: 'localhost', port: 80 }
overrides = { port: 3000, debug: true }

merged = defaults.merge(overrides)
# { host: 'localhost', port: 3000, debug: true }

# Merge with block for conflict resolution
merged = defaults.merge(overrides) { |_key, old, new| old }
# { host: 'localhost', port: 80, debug: true }

# --- Hash#transform_keys ---
old_hash = { 'name' => 'Alice', 'age' => 30 }
new_hash = old_hash.transform_keys(&:to_sym)
# { name: 'Alice', age: 30 }

# --- Hash#dig (deep access, Ruby 2.3+) ---
data = {
  user: {
    profile: {
      name: 'Alice',
      address: { city: 'NYC' }
    }
  }
}

puts data.dig(:user, :profile, :name)         # 'Alice'
puts data.dig(:user, :profile, :address, :city) # 'NYC'
puts data.dig(:user, :missing, :key)           # nil (no error)

# --- Keyword arguments ---
def greet(name:, greeting: 'Hello', punctuation: '!')
  "#{greeting}, #{name}#{punctuation}"
end

puts greet(name: 'Alice')                       # Hello, Alice!
puts greet(name: 'Bob', greeting: 'Hi')         # Hi, Bob!

# --- ** splat (double splat) ---
def create_user(**attrs)
  # attrs is a Hash
  puts "Creating user with: #{attrs.inspect}"
end

create_user(name: 'Alice', role: 'admin')

# Merge keyword args with defaults
def configure(host:, port: 8080, **extras)
  puts "Host: #{host}, Port: #{port}"
  puts "Extra: #{extras}" unless extras.empty?
end

configure(host: 'example.com', port: 3000, debug: true, ssl: true)
# Host: example.com, Port: 3000
# Extra: {:debug=>true, :ssl=>true}

# --- Hash to keyword args ---
params = { name: 'Alice', age: 30 }
# some_method(**params)  # expands hash into keyword args
""",
    ),

    # 14. Modules as Namespaces & Mixins
    (
        "ruby/modules-namespaces-mixins.md",
        "ruby",
        ["architecture", "pattern"],
        "Modules as Namespaces & Mixins",
        "Module nesting, namespace, Enumerable/Comparable custom implementations, Rails Concerns.",
        "pattern",
        "# --- Namespacing ---\n" +
        "module Acme\n" +
        "  module Api\n" +
        "    module V1\n" +
        "      class UsersController\n" +
        "        def index\n" +
        "          'Listing users'\n" +
        "        end\n" +
        "      end\n" +
        "    end\n" +
        "  end\n" +
        "end\n" +
        "\n" +
        "controller = Acme::Api::V1::UsersController.new\n" +
        "puts controller.index\n" +
        "\n" +
        "# Module with nested constants\n" +
        "module Config\n" +
        "  DEFAULTS = {\n" +
        "    host: 'localhost',\n" +
        "    port: 3000\n" +
        "  }.freeze\n" +
        "\n" +
        "  module Database\n" +
        "    ADAPTER = 'postgresql'\n" +
        "  end\n" +
        "end\n" +
        "\n" +
        "puts Config::DEFAULTS[:host]        # localhost\n" +
        "puts Config::Database::ADAPTER       # postgresql\n" +
        "\n" +
        "# --- Custom Enumerable ---\n" +
        "class Playlist\n" +
        "  include Enumerable\n" +
        "\n" +
        "  def initialize(*songs)\n" +
        "    @songs = songs\n" +
        "  end\n" +
        "\n" +
        "  def each(&block)\n" +
        "    @songs.each(&block)\n" +
        "  end\n" +
        "end\n" +
        "\n" +
        "playlist = Playlist.new('Song A', 'Song B', 'Song C')\n" +
        "puts playlist.map(&:upcase).join(', ')  # SONG A, SONG B, SONG C\n" +
        "puts playlist.first                      # Song A\n" +
        "puts playlist.any? { |s| s.start_with?('A') }  # false\n" +
        "\n" +
        "# --- Custom Comparable ---\n" +
        "class Person\n" +
        "  include Comparable\n" +
        "\n" +
        "  attr_reader :name, :age\n" +
        "\n" +
        "  def initialize(name, age)\n" +
        "    @name = name\n" +
        "    @age = age\n" +
        "  end\n" +
        "\n" +
        "  def <=>(other)\n" +
        "    age <=> other.age\n" +
        "  end\n" +
        "end\n" +
        "\n" +
        "alice = Person.new('Alice', 30)\n" +
        "bob   = Person.new('Bob', 25)\n" +
        "puts alice > bob   # true\n" +
        "puts [bob, alice].sort.map(&:name).join(', ')  # Bob, Alice\n" +
        "\n" +
        "# --- Rails-style Concern ---\n" +
        "# (Pure Ruby equivalent)\n" +
        "module Taggable\n" +
        "  def self.included(base)\n" +
        "    base.extend(ClassMethods)\n" +
        "  end\n" +
        "\n" +
        "  module ClassMethods\n" +
        "    def taggable?\n" +
        "      true\n" +
        "    end\n" +
        "  end\n" +
        "\n" +
        "  def tags\n" +
        "    @tags ||= []\n" +
        "  end\n" +
        "\n" +
        "  def add_tag(tag)\n" +
        "    tags << tag\n" +
        "  end\n" +
        "end\n" +
        "\n" +
        "class Article\n" +
        "  include Taggable\n" +
        "end\n" +
        "\n" +
        "article = Article.new\n" +
        "article.add_tag('ruby')\n" +
        "puts article.tags.inspect          # ['ruby']\n" +
        "puts Article.taggable?              # true\n",
    ),

    # 15. CLI & Thor
    (
        "ruby/cli-thor.md",
        "ruby",
        ["cli", "pattern"],
        "CLI & Thor",
        "ARGV, OptionParser, Thor CLI framework: subcommands, options, defaults.",
        "pattern",
        """require 'optparse'
require 'thor'

# --- ARGV basics ---
# Run: ruby script.rb --name=Alice --verbose
name    = ARGV[0] || 'World'
verbose = ARGV.include?('--verbose')
puts "Hello, #{name}!"
puts 'Verbose mode' if verbose

# --- OptionParser ---
params = {}
OptionParser.new do |opts|
  opts.banner = 'Usage: script.rb [options]'

  opts.on('-n', '--name NAME', 'Name to greet') do |n|
    params[:name] = n
  end

  opts.on('-v', '--[no-]verbose', 'Run verbosely') do |v|
    params[:verbose] = v
  end

  opts.on('-c', '--count N', Integer, 'Repeat count') do |c|
    params[:count] = c
  end

  opts.on('-h', '--help', 'Show help') do
    puts opts
    exit
  end
end.parse!

name = params[:name] || 'World'
puts "Hello, #{name}!" * (params[:count] || 1)

# --- Thor CLI (gem install thor) ---
class MyCLI < Thor
  desc 'hello NAME', 'Greet someone'
  option :yell, type: :boolean, aliases: '-y', desc: 'Yell the greeting'
  option :repeat, type: :numeric, default: 1, aliases: '-r'
  def hello(name = 'World')
    greeting = "Hello, #{name}!"
    greeting = greeting.upcase if options[:yell]
    options[:repeat].times { puts greeting }
  end

  desc 'serve', 'Start the server'
  option :port, type: :numeric, default: 3000, aliases: '-p'
  option :env, type: :string, default: 'development', aliases: '-e'
  def serve
    puts "Starting server on port #{options[:port]} (#{options[:env]} env)"
    # Server start logic here
  end

  desc 'generate TYPE NAME', 'Generate a scaffold'
  subcommand 'generate', GenerateCommands

  method_option :force, type: :boolean, aliases: '-f', desc: 'Overwrite existing files'
  def scaffold(name)
    puts "Generating scaffold for #{name}"
  end

  # Default task
  default_task :hello
end

# Subcommand class
class GenerateCommands < Thor
  desc 'model NAME', 'Generate a model'
  option :fields, type: :array, aliases: '-f'
  def model(name)
    fields = (options[:fields] || %w[name email]).join(', ')
    puts "Generating model #{name} with fields: #{fields}"
  end

  desc 'controller NAME', 'Generate a controller'
  option :actions, type: :array, aliases: '-a', default: %w[index show]
  def controller(name)
    puts "Generating #{name} controller with actions: #{options[:actions].join(', ')}"
  end
end

# To run:
#   ruby script.rb hello Alice --yell
#   ruby script.rb help
#   ruby script.rb serve --port=4567
#   ruby script.rb generate model User --fields name email age
""",
    ),
]
