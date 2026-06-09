"""Java snippets — 20 entries covering the core Java ecosystem (Java 17+)."""

SNIPPETS = [
    # ═══════════════════════════════════════════════════════════
    # 1. Classes, Records & Sealed Classes
    # ═══════════════════════════════════════════════════════════
    ("java/records-classes.md", "java", ["pattern", "util"],
     "Classes, Records & Sealed Classes", "Modern Java classes, records for data carriers, and sealed hierarchies with permits.", "pattern",
     """// Record — concise data carrier (Java 16+)
public record Point(int x, int y) {}

// Sealed hierarchy (Java 17+)
public sealed interface Shape permits Circle, Rectangle {}

public record Circle(double radius) implements Shape {}
public record Rectangle(double width, double height) implements Shape {}

// Static nested class with access modifiers
public class Outer {
    private static int counter = 0;

    public static class Nested {
        public void increment() {
            counter++;
        }
    }

    public static void main(String[] args) {
        Point p = new Point(3, 4);
        System.out.println("x = " + p.x());  // accessor, not getX()

        Shape s = new Circle(5.0);
        if (s instanceof Circle c) {
            System.out.println("Area: " + Math.PI * c.radius() * c.radius());
        }

        Nested n = new Nested();
        n.increment();
        n.increment();
        System.out.println("Counter: " + counter);
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 2. Streams & Lambdas
    # ═══════════════════════════════════════════════════════════
    ("java/streams-lambdas.md", "java", ["pattern", "util"],
     "Streams & Lambdas", "Stream API with map/filter/reduce/collect/groupingBy/toList, lambda syntax, and method references.", "pattern",
     """import java.util.*;
import java.util.stream.*;

public class StreamDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Alice", "Bob", "Charlie", "Diana", "Alex");

        // Filter + map + collect
        List<String> upperLong = names.stream()
                .filter(n -> n.length() > 3)
                .map(String::toUpperCase)
                .collect(Collectors.toList());
        System.out.println(upperLong);  // [ALICE, CHARLIE, DIANA]

        // groupingBy
        Map<Integer, List<String>> byLength = names.stream()
                .collect(Collectors.groupingBy(String::length));
        System.out.println(byLength);   // {3=[Bob, Alex], 5=[Alice, Diana], 7=[Charlie]}

        // reduce
        int sum = Stream.of(1, 2, 3, 4, 5)
                .reduce(0, Integer::sum);
        System.out.println(sum);        // 15

        // toList (Java 16+)
        var doubled = Stream.of(2, 4, 6)
                .map(n -> n * 2)
                .toList();
        System.out.println(doubled);    // [4, 8, 12]

        // Method reference ::
        names.forEach(System.out::println);
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 3. Generics & Collections
    # ═══════════════════════════════════════════════════════════
    ("java/generics-collections.md", "java", ["pattern", "util"],
     "Generics & Collections", "Generic classes/methods, wildcards (? extends T), and typed collections with List/Set/Map.", "pattern",
     """import java.util.*;

// Generic class
public class Box<T> {
    private T value;

    public Box(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    // Generic method
    public static <U> Box<U> of(U item) {
        return new Box<>(item);
    }

    // Wildcard — accepts any Number subtype
    public static double sumOf(Box<? extends Number> box) {
        return box.get().doubleValue();
    }

    public static void main(String[] args) {
        Box<String> stringBox = new Box<>("Hello");
        System.out.println(stringBox.get());

        Box<Integer> intBox = Box.of(42);
        System.out.println(sumOf(intBox));      // 42.0

        Box<Double> dblBox = Box.of(3.14);
        System.out.println(sumOf(dblBox));      // 3.14

        // Typed collections
        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
        Set<String> nameSet = new HashSet<>(Set.of("Alice", "Bob"));
        Map<String, Integer> scores = new HashMap<>(Map.of("Alice", 95, "Bob", 87));

        // Collections utility
        Collections.sort(numbers);
        Collections.reverse(numbers);
        System.out.println(numbers);            // [3, 2, 1]
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 4. Exception Handling
    # ═══════════════════════════════════════════════════════════
    ("java/exception-handling.md", "java", ["pattern", "util"],
     "Exception Handling", "Try-catch-finally, try-with-resources, multi-catch, checked vs unchecked exceptions, custom exceptions.", "pattern",
     """import java.io.*;

// Custom checked exception
class InsufficientFundsException extends Exception {
    public InsufficientFundsException(String message) {
        super(message);
    }
}

// Custom unchecked exception
class AccountNotFoundException extends RuntimeException {
    public AccountNotFoundException(String id) {
        super("Account not found: " + id);
    }
}

public class BankTransfer {
    public static void transfer(String fromId, double amount)
            throws InsufficientFundsException {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (amount > 1000) {
            throw new InsufficientFundsException("Insufficient funds: " + amount);
        }
        System.out.println("Transferred $" + amount);
    }

    public static void main(String[] args) {
        // Multi-catch
        try {
            transfer("ACC-001", 2000);
        } catch (InsufficientFundsException | IllegalArgumentException e) {
            System.err.println("Transfer error: " + e.getMessage());
        } finally {
            System.out.println("Transfer attempt finished");
        }

        // Try-with-resources (auto-closeable)
        try (BufferedReader br = new BufferedReader(
                new StringReader("Hello\\nWorld"))) {
            String line;
            while ((line = br.readLine()) != null) {
                System.out.println(line);
            }
        } catch (IOException e) {
            System.err.println("IO error: " + e.getMessage());
        }

        // Checked vs unchecked
        throw new AccountNotFoundException("ACC-999");  // runtime, no throws needed
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 5. File I/O (java.nio.file)
    # ═══════════════════════════════════════════════════════════
    ("java/file-io.md", "java", ["pattern", "io"],
     "File I/O (java.nio.file)", "Reading/writing files, streaming lines, walking directories, Path and BufferedReader with try-resources.", "pattern",
     """import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

public class FileIODemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("demo.txt");

        // Write lines
        Files.writeString(path, "Hello\\nWorld\\nJava 17");

        // Read all lines
        List<String> lines = Files.readAllLines(path);
        lines.forEach(System.out::println);

        // Stream lines (lazy)
        try (Stream<String> stream = Files.lines(path)) {
            stream.filter(l -> l.startsWith("J"))
                  .forEach(System.out::println);  // Java 17
        }

        // Walk directory tree
        try (Stream<Path> walk = Files.walk(Path.of("."), 2)) {
            walk.filter(Files::isRegularFile)
                .forEach(p -> System.out.println(p + " (" + Files.size(p) + " bytes)"));
        }

        // BufferedReader with try-resources
        try (BufferedReader br = Files.newBufferedReader(
                Path.of("demo.txt"), java.nio.charset.StandardCharsets.UTF_8)) {
            br.lines().forEach(System.out::println);
        }

        // BufferedWriter
        try (BufferedWriter bw = Files.newBufferedWriter(
                Path.of("output.txt"))) {
            bw.write("Generated content");
            bw.newLine();
        }

        // Cleanup
        Files.deleteIfExists(path);
        Files.deleteIfExists(Path.of("output.txt"));
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 6. JSON Processing (Jackson)
    # ═══════════════════════════════════════════════════════════
    ("java/jackson-json.md", "java", ["pattern", "io", "framework"],
     "JSON Processing (Jackson)", "ObjectMapper, @JsonProperty, readValue/writeValueAsString, Jackson annotations for serialization.", "pattern",
     '''import com.fasterxml.jackson.annotation.*;
import com.fasterxml.jackson.databind.*;
import java.util.*;

// Jackson annotations
record Book(
    @JsonProperty("isbn") String isbn,
    @JsonProperty("title") String title,
    @JsonProperty("author") String author,
    @JsonProperty("year") int year
) {}

@JsonIgnoreProperties(ignoreUnknown = true)
record ApiResponse(
    @JsonProperty("status") String status,
    @JsonProperty("data") List<Book> data
) {}

public class JacksonDemo {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        mapper.findAndRegisterModules();

        // Java object -> JSON
        Book book = new Book("978-3-16-148410-0", "Effective Java",
                             "Joshua Bloch", 2018);
        String json = mapper.writeValueAsString(book);
        System.out.println(json);
        // {"isbn":"978-3-16-148410-0","title":"Effective Java",...}

        // JSON -> Java object
        Book parsed = mapper.readValue(json, Book.class);
        System.out.println(parsed.title());  // Effective Java

        // Pretty print
        String pretty = mapper.writerWithDefaultPrettyPrinter()
                               .writeValueAsString(book);
        System.out.println(pretty);

        // List deserialization
        String listJson = """
                [{"isbn":"A","title":"T1","author":"A1","year":2020},
                 {"isbn":"B","title":"T2","author":"A2","year":2021}]
                """;
        List<Book> books = mapper.readValue(listJson,
                mapper.getTypeFactory().constructCollectionType(List.class, Book.class));
        System.out.println(books.size());  // 2
    }
}
'''),

    # ═══════════════════════════════════════════════════════════
    # 7. Maven/Gradle Build
    # ═══════════════════════════════════════════════════════════
    ("java/build-files.md", "java", ["pattern", "tool"],
     "Maven/Gradle Build", "Maven pom.xml and Gradle build.gradle with dependencies, plugins, and build configuration.", "pattern",
     """<!-- pom.xml — Maven build configuration -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>my-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <!-- Jackson -->
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.15.2</version>
        </dependency>
        <!-- JUnit 5 -->
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.0</version>
            <scope>test</scope>
        </dependency>
        <!-- SLF4J + Logback -->
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.4.11</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.11.0</version>
            </plugin>
        </plugins>
    </build>
</project>

// --- build.gradle — Gradle build configuration ---
plugins {
    id 'java'
    id 'application'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.15.2'
    implementation 'ch.qos.logback:logback-classic:1.4.11'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.0'
}

application {
    mainClass = 'com.example.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 8. Spring Boot REST API
    # ═══════════════════════════════════════════════════════════
    ("java/spring-boot-rest.md", "java", ["pattern", "framework"],
     "Spring Boot REST API", "@RestController, @GetMapping/PostMapping, @RequestBody, @PathVariable, and @Service layered architecture.", "pattern",
     """import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.*;
import org.springframework.stereotype.Service;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}

// --- Record DTO ---
record UserDto(Long id, String name, String email) {}

// --- Service Layer ---
@Service
class UserService {
    private final Map<Long, UserDto> store = new ConcurrentHashMap<>();
    private long nextId = 1;

    public List<UserDto> findAll() {
        return List.copyOf(store.values());
    }

    public Optional<UserDto> findById(Long id) {
        return Optional.ofNullable(store.get(id));
    }

    public UserDto create(UserDto dto) {
        UserDto saved = new UserDto(nextId++, dto.name(), dto.email());
        store.put(saved.id(), saved);
        return saved;
    }
}

// --- REST Controller ---
@RestController
@RequestMapping("/api/users")
class UserController {
    private final UserService userService;

    UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping
    public List<UserDto> getAll() {
        return userService.findAll();
    }

    @GetMapping("/{id}")
    public UserDto getById(@PathVariable Long id) {
        return userService.findById(id)
                .orElseThrow(() -> new NoSuchElementException("User not found: " + id));
    }

    @PostMapping
    public UserDto create(@RequestBody UserDto dto) {
        return userService.create(dto);
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 9. JUnit 5 Testing
    # ═══════════════════════════════════════════════════════════
    ("java/junit5-testing.md", "java", ["pattern", "testing"],
     "JUnit 5 Testing", "@Test, @ParameterizedTest, @BeforeEach, assertions, @Mock with Mockito, and assertThrows.", "pattern",
     """import org.junit.jupiter.api.*;
import org.junit.jupiter.params.*;
import org.junit.jupiter.params.provider.*;
import org.mockito.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class Calculator {
    public int add(int a, int b) {
        return a + b;
    }

    public int divide(int a, int b) {
        if (b == 0) throw new ArithmeticException("Division by zero");
        return a / b;
    }
}

interface UserRepository {
    Optional<String> findNameById(Long id);
}

class UserService {
    private final UserRepository repo;

    UserService(UserRepository repo) {
        this.repo = repo;
    }

    public String getName(Long id) {
        return repo.findNameById(id)
                .orElseThrow(() -> new NoSuchElementException("User " + id + " not found"));
    }
}

class CalculatorTest {
    private Calculator calc;

    @BeforeEach
    void setUp() {
        calc = new Calculator();
    }

    @Test
    void testAdd() {
        assertEquals(5, calc.add(2, 3));
    }

    @Test
    void testDivisionByZero() {
        ArithmeticException ex = assertThrows(ArithmeticException.class,
                () -> calc.divide(5, 0));
        assertEquals("Division by zero", ex.getMessage());
    }

    @ParameterizedTest
    @CsvSource({"1,2,3", "10,20,30", "0,0,0"})
    void testAddParameterized(int a, int b, int expected) {
        assertEquals(expected, calc.add(a, b));
    }
}

class UserServiceTest {
    @Mock
    private UserRepository repo;

    @InjectMocks
    private UserService service;

    @BeforeEach
    void initMocks() {
        MockitoAnnotations.openMocks(this);
    }

    @Test
    void testGetNameFound() {
        when(repo.findNameById(1L)).thenReturn(Optional.of("Alice"));
        assertEquals("Alice", service.getName(1L));
        verify(repo).findNameById(1L);
    }

    @Test
    void testGetNameNotFound() {
        when(repo.findNameById(99L)).thenReturn(Optional.empty());
        assertThrows(NoSuchElementException.class, () -> service.getName(99L));
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 10. Optional & Null Safety
    # ═══════════════════════════════════════════════════════════
    ("java/optional-null-safety.md", "java", ["pattern", "util"],
     "Optional & Null Safety", "Optional.of/empty/ofNullable, orElse/orElseThrow, ifPresent, map/filter on Optional.", "pattern",
     """import java.util.*;

public class OptionalDemo {
    public static Optional<String> findUserEmail(Long id) {
        Map<Long, String> db = Map.of(1L, "alice@example.com");
        return Optional.ofNullable(db.get(id));
    }

    public static void main(String[] args) {
        // Creation
        Optional<String> present = Optional.of("hello");
        Optional<String> absent = Optional.empty();
        Optional<String> nullable = Optional.ofNullable(null);

        // Retrieval with defaults
        String val1 = absent.orElse("default");
        String val2 = absent.orElseGet(() -> "computed default");
        // String val3 = absent.orElseThrow();          // Java 10+
        // String val4 = absent.orElseThrow(() -> new NoSuchElementException("missing"));

        System.out.println(val1);  // default

        // ifPresent
        present.ifPresent(s -> System.out.println("Found: " + s));  // Found: hello

        // map / filter
        Optional<Integer> length = present.map(String::length);
        System.out.println(length.orElse(0));  // 5

        Optional<String> filtered = present.filter(s -> s.startsWith("h"));
        System.out.println(filtered.isPresent());  // true

        // Chaining with flatMap
        Optional<String> email = findUserEmail(1L)
                .filter(e -> e.contains("@"))
                .map(String::toLowerCase);
        System.out.println(email.orElse("no email"));  // alice@example.com

        // Avoid: Optional.ofNullable(getValue()) for method return types
        // Avoid: Optional as method parameter — overload instead
        // Avoid: Optional in fields / serialization
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 11. JDBC & H2 Database
    # ═══════════════════════════════════════════════════════════
    ("java/jdbc-h2.md", "java", ["pattern", "database"],
     "JDBC & H2 Database", "DriverManager, Connection, PreparedStatement, ResultSet, executeQuery/executeUpdate with H2 in-memory DB.", "pattern",
     '''import java.sql.*;

public class JdbcDemo {
    public static void main(String[] args) throws Exception {
        // H2 in-memory database (add h2-2.2.x.jar to classpath)
        String url = "jdbc:h2:mem:testdb";
        String user = "sa";
        String pass = "";

        try (Connection conn = DriverManager.getConnection(url, user, pass);
             Statement stmt = conn.createStatement()) {

            // Create table
            stmt.executeUpdate("""
                    CREATE TABLE users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        email VARCHAR(100)
                    )
                    """);

            // Insert with PreparedStatement
            try (PreparedStatement ps = conn.prepareStatement(
                    "INSERT INTO users (name, email) VALUES (?, ?)")) {
                ps.setString(1, "Alice");
                ps.setString(2, "alice@example.com");
                ps.executeUpdate();

                ps.setString(1, "Bob");
                ps.setString(2, "bob@example.com");
                ps.executeUpdate();
            }

            // Query
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT * FROM users WHERE name = ?")) {
                ps.setString(1, "Alice");
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        int id = rs.getInt("id");
                        String name = rs.getString("name");
                        String email = rs.getString("email");
                        System.out.printf("User: id=%d, name=%s, email=%s%n",
                                          id, name, email);
                    }
                }
            }

            // Count
            try (ResultSet rs = stmt.executeQuery("SELECT COUNT(*) FROM users")) {
                if (rs.next()) {
                    System.out.println("Total users: " + rs.getInt(1));
                }
            }
        }
    }
}
'''),

    # ═══════════════════════════════════════════════════════════
    # 12. Concurrency
    # ═══════════════════════════════════════════════════════════
    ("java/concurrency.md", "java", ["pattern", "concurrency"],
     "Concurrency", "Thread, Runnable, ExecutorService, CompletableFuture, synchronized, volatile, and ReentrantLock.", "pattern",
     """import java.util.concurrent.*;
import java.util.concurrent.locks.*;
import java.util.stream.*;

public class ConcurrencyDemo {
    private static int sharedCounter = 0;
    private static final Lock lock = new ReentrantLock();

    static class CounterTask implements Runnable {
        private final int increments;

        CounterTask(int increments) {
            this.increments = increments;
        }

        @Override
        public void run() {
            for (int i = 0; i < increments; i++) {
                lock.lock();
                try {
                    sharedCounter++;
                } finally {
                    lock.unlock();
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        // Basic thread
        Thread t = new Thread(() -> System.out.println("Hello from thread"));
        t.start();
        t.join();

        // ExecutorService
        ExecutorService executor = Executors.newFixedThreadPool(4);
        var futures = IntStream.range(0, 10)
                .mapToObj(i -> executor.submit(() -> {
                    Thread.sleep(ThreadLocalRandom.current().nextInt(100));
                    return i * i;
                }))
                .toList();

        for (var f : futures) {
            System.out.println("Result: " + f.get());
        }
        executor.shutdown();

        // CompletableFuture
        CompletableFuture.supplyAsync(() -> "Hello")
                .thenApply(s -> s + " World")
                .thenAccept(System.out::println)
                .join();

        // synchronized block
        var sb = new StringBuffer();
        synchronized (sb) {
            sb.append("Thread-safe append");
        }

        // volatile: use for visibility flags
        class Runner {
            volatile boolean running = true;
        }
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 13. DateTime API (java.time)
    # ═══════════════════════════════════════════════════════════
    ("java/datetime-api.md", "java", ["pattern", "util"],
     "Date-Time API (java.time)", "LocalDate, LocalDateTime, ZonedDateTime, DateTimeFormatter, Duration, and Period.", "pattern",
     """import java.time.*;
import java.time.format.*;
import java.time.temporal.*;

public class DateTimeDemo {
    public static void main(String[] args) {
        // LocalDate
        LocalDate today = LocalDate.now();
        LocalDate independenceDay = LocalDate.of(1776, Month.JULY, 4);
        Period between = Period.between(independenceDay, today);
        System.out.printf("%d years, %d months, %d days%n",
                          between.getYears(), between.getMonths(), between.getDays());

        // LocalDateTime
        LocalDateTime now = LocalDateTime.now();
        LocalDateTime meeting = LocalDateTime.of(2025, 6, 10, 14, 30);
        Duration duration = Duration.between(now, meeting);
        System.out.println("Hours until meeting: " + duration.toHours());

        // ZonedDateTime
        ZonedDateTime nyc = ZonedDateTime.now(ZoneId.of("America/New_York"));
        ZonedDateTime paris = nyc.withZoneSameInstant(ZoneId.of("Europe/Paris"));
        System.out.println("NYC: " + nyc + " -> Paris: " + paris);

        // Formatting
        DateTimeFormatter fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        System.out.println("Formatted: " + now.format(fmt));

        DateTimeFormatter isoFmt = DateTimeFormatter.ISO_LOCAL_DATE_TIME;
        LocalDateTime parsed = LocalDateTime.parse("2025-06-10T14:30:00", isoFmt);
        System.out.println("Parsed: " + parsed);

        // Arithmetic
        LocalDate nextWeek = today.plusWeeks(1);
        LocalDate lastMonth = today.minus(1, ChronoUnit.MONTHS);
        System.out.println("Next week: " + nextWeek + ", Last month: " + lastMonth);

        // Instant (machine time)
        Instant epoch = Instant.EPOCH;
        Instant nowInstant = Instant.now();
        System.out.println("Seconds since epoch: " + Duration.between(epoch, nowInstant).getSeconds());
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 14. Annotations & Reflection
    # ═══════════════════════════════════════════════════════════
    ("java/annotations-reflection.md", "java", ["pattern", "meta"],
     "Annotations & Reflection", "@Retention, @Target, custom annotation, Method.getAnnotation, field access via reflection.", "pattern",
     """import java.lang.annotation.*;
import java.lang.reflect.*;

// Custom annotation
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.FIELD})
@interface JsonField {
    String name() default "";
    boolean required() default true;
}

// Usage
class User {
    @JsonField(name = "user_id")
    private long id;

    @JsonField(name = "full_name")
    private String name;

    public User(long id, String name) {
        this.id = id;
        this.name = name;
    }

    @JsonField
    public String getInfo() {
        return name + " (" + id + ")";
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}

public class ReflectionDemo {
    public static void main(String[] args) throws Exception {
        User user = new User(42, "Alice");

        // Class reflection
        Class<?> clazz = user.getClass();
        System.out.println("Class: " + clazz.getSimpleName());

        // Field reflection with annotation
        for (Field field : clazz.getDeclaredFields()) {
            JsonField annot = field.getAnnotation(JsonField.class);
            if (annot != null) {
                field.setAccessible(true);
                Object value = field.get(user);
                String jsonName = annot.name().isEmpty()
                        ? field.getName()
                        : annot.name();
                System.out.printf("  \"%s\": \"%s\", required=%b%n",
                                  jsonName, value, annot.required());
            }
        }

        // Method reflection with annotation
        for (Method method : clazz.getDeclaredMethods()) {
            if (method.isAnnotationPresent(JsonField.class)) {
                System.out.println("Annotated method: " + method.getName());
                System.out.println("  -> " + method.invoke(user));
            }
        }
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 15. HTTP Client (java.net.http)
    # ═══════════════════════════════════════════════════════════
    ("java/http-client.md", "java", ["pattern", "networking"],
     "HTTP Client (java.net.http)", "HttpClient, HttpRequest, HttpResponse, async send, BodyHandlers, and custom headers.", "pattern",
     """import java.net.URI;
import java.net.http.*;
import java.net.http.HttpResponse.BodyHandlers;
import java.util.concurrent.*;

public class HttpClientDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();

        // Synchronous GET
        HttpRequest getReq = HttpRequest.newBuilder()
                .uri(URI.create("https://httpbin.org/get"))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> syncResp = client.send(getReq, BodyHandlers.ofString());
        System.out.println("GET status: " + syncResp.statusCode());
        System.out.println("GET body (first 200 chars): " +
                           syncResp.body().substring(0, Math.min(200, syncResp.body().length())));

        // Asynchronous GET
        CompletableFuture<HttpResponse<String>> future = client.sendAsync(
                getReq, BodyHandlers.ofString());
        future.thenApply(HttpResponse::body)
              .thenAccept(body -> System.out.println("Async body length: " + body.length()))
              .join();

        // POST with JSON body
        String json = "{\"name\": \"Alice\", \"email\": \"alice@example.com\"}";
        HttpRequest postReq = HttpRequest.newBuilder()
                .uri(URI.create("https://httpbin.org/post"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        HttpResponse<String> postResp = client.send(postReq, BodyHandlers.ofString());
        System.out.println("POST status: " + postResp.statusCode());

        // Headers from response
        postResp.headers().map().forEach((k, v) ->
                System.out.println("  Header: " + k + " = " + v));
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 16. Enums & Pattern Matching
    # ═══════════════════════════════════════════════════════════
    ("java/enums-pattern-matching.md", "java", ["pattern", "util"],
     "Enums & Pattern Matching", "Enum with fields/methods, switch expressions, pattern matching for switch (Java 17+), and yield.", "pattern",
     """// Enum with fields and methods
enum HttpStatus {
    OK(200, "OK"),
    CREATED(201, "Created"),
    NOT_FOUND(404, "Not Found"),
    INTERNAL_SERVER_ERROR(500, "Internal Server Error");

    private final int code;
    private final String reason;

    HttpStatus(int code, String reason) {
        this.code = code;
        this.reason = reason;
    }

    public int code() { return code; }
    public String reason() { return reason; }

    public boolean isError() {
        return code >= 400;
    }

    public static HttpStatus fromCode(int code) {
        for (var s : values()) {
            if (s.code == code) return s;
        }
        throw new IllegalArgumentException("Unknown code: " + code);
    }
}

// Sealed interface for pattern matching
sealed interface Payment permits Cash, Card, Transfer {}
record Cash(double amount) implements Payment {}
record Card(String cardNumber, double amount) implements Payment {}
record Transfer(String iban, double amount) implements Payment {}

public class EnumPatternDemo {
    // Switch expression with pattern matching (Java 17+ preview, Java 21+ stable)
    static String describePayment(Payment p) {
        return switch (p) {
            case Cash c -> "Cash: $" + c.amount();
            case Card c -> "Card ****" + c.cardNumber().substring(c.cardNumber().length() - 4)
                           + ": $" + c.amount();
            case Transfer t -> "Transfer to IBAN " + t.iban() + ": $" + t.amount();
        };
    }

    static String describeStatus(HttpStatus s) {
        return switch (s) {
            case OK       -> "Success";
            case CREATED  -> "Created";
            case NOT_FOUND -> "Not Found (404)";
            default      -> {
                String msg = s.code() + " " + s.reason();
                yield msg + " — " + (s.isError() ? "Error" : "Info");
            }
        };
    }

    public static void main(String[] args) {
        System.out.println(HttpStatus.OK.code());                       // 200
        System.out.println(HttpStatus.fromCode(404).reason());           // Not Found

        System.out.println(describePayment(new Cash(25.50)));            // Cash: $25.5
        System.out.println(describePayment(new Card("1234567890123456", 99.99)));

        System.out.println(describeStatus(HttpStatus.CREATED));
        System.out.println(describeStatus(HttpStatus.INTERNAL_SERVER_ERROR));
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 17. Logging (SLF4J + Logback)
    # ═══════════════════════════════════════════════════════════
    ("java/slf4j-logback.md", "java", ["pattern", "logging"],
     "Logging (SLF4J + Logback)", "LoggerFactory, log levels, MDC for contextual logging, parameterized messages, logback.xml config.", "pattern",
     """import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class LoggingDemo {
    // SLF4J logger — no direct Logback dependency in code
    private static final Logger log = LoggerFactory.getLogger(LoggingDemo.class);

    public static void main(String[] args) {
        // Parameterized logging (avoids string concatenation)
        String user = "Alice";
        int count = 42;
        log.info("User {} has {} items in cart", user, count);
        log.debug("Processing order for user: {}", user);

        // Error logging with exception
        try {
            riskyOperation();
        } catch (Exception e) {
            log.error("Operation failed for user {}", user, e);
        }

        // MDC (Mapped Diagnostic Context) — per-thread context
        MDC.put("requestId", "req-" + System.currentTimeMillis());
        MDC.put("userId", user);
        log.info("Processing payment");
        processPayment();
        MDC.clear();

        // Level-specific checks (useful for expensive log construction)
        if (log.isTraceEnabled()) {
            log.trace("Expensive detail: {}", expensiveCall());
        }
    }

    static void riskyOperation() {
        throw new RuntimeException("Timeout");
    }

    static String expensiveCall() {
        return "expensive-result";
    }

    static void processPayment() {
        // MDC is inherited by the current thread
        Logger paymentLog = LoggerFactory.getLogger("payment");
        paymentLog.info("Payment processed");
    }
}

// --- src/main/resources/logback.xml ---
/*
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} [%X{requestId}] — %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/app.%d{yyyy-MM-dd}.log</fileNamePattern>
            <maxHistory>30</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} [%thread] %-5level %logger{36} — %msg%n</pattern>
        </encoder>
    </appender>

    <root level="info">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>

    <logger name="payment" level="debug" additivity="false">
        <appender-ref ref="CONSOLE"/>
    </logger>
</configuration>
*/
"""),

    # ═══════════════════════════════════════════════════════════
    # 18. Records, Text Blocks & Switch
    # ═══════════════════════════════════════════════════════════
    ("java/text-blocks-switch.md", "java", ["pattern", "util"],
     "Records, Text Blocks & Switch", "Text block \"\"\" syntax, record classes, enhanced switch with yield, and pattern matching.", "pattern",
     '''// Record
public record Product(String sku, String name, double price) {}

public class RecordsTextBlocksDemo {
    public static void main(String[] args) {
        // Text block (Java 13+)
        String html = """
                <html>
                    <body>
                        <h1>Hello, %s!</h1>
                        <p>Price: $%.2f</p>
                    </body>
                </html>
                """.formatted("Widget A", 19.99);
        System.out.println(html);

        // JSON text block
        String json = """
                {
                    "sku": "WID-001",
                    "name": "Widget A",
                    "price": 19.99
                }
                """;
        System.out.println(json.stripIndent());

        // Record usage
        Product p = new Product("WID-001", "Widget A", 19.99);
        System.out.println(p.name() + " — $" + p.price());

        // Switch with yield (Java 14+)
        String dayName = "WEDNESDAY";
        int dayNumber = switch (dayName) {
            case "MONDAY"    -> 1;
            case "TUESDAY"   -> 2;
            case "WEDNESDAY" -> 3;
            case "THURSDAY"  -> 4;
            case "FRIDAY"    -> 5;
            case "SATURDAY"  -> 6;
            case "SUNDAY"    -> 7;
            default          -> {
                System.err.println("Invalid day: " + dayName);
                yield -1;
            }
        };
        System.out.println(dayName + " is day " + dayNumber);

        // Pattern matching for instanceof (Java 16+)
        Object obj = p;
        if (obj instanceof Product product) {
            System.out.println("Matched product: " + product.name());
        }
    }
}
'''),

    # ═══════════════════════════════════════════════════════════
    # 19. CompletableFuture
    # ═══════════════════════════════════════════════════════════
    ("java/completablefuture.md", "java", ["pattern", "concurrency"],
     "CompletableFuture", "supplyAsync, thenApply/thenCompose, allOf, exceptionally, join, and custom thread pool.", "pattern",
     """import java.util.concurrent.*;
import java.util.stream.*;

public class CompletableFutureDemo {
    private static final ExecutorService CUSTOM_POOL =
            Executors.newFixedThreadPool(4);

    static CompletableFuture<String> fetchUser(Long id) {
        return CompletableFuture.supplyAsync(() -> {
            simulateDelay(200);
            return "User-" + id;
        }, CUSTOM_POOL);
    }

    static CompletableFuture<String> fetchOrders(String user) {
        return CompletableFuture.supplyAsync(() -> {
            simulateDelay(150);
            return user + " has 3 orders";
        }, CUSTOM_POOL);
    }

    static void simulateDelay(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) {
        // Chaining: thenApply
        CompletableFuture.supplyAsync(() -> 5, CUSTOM_POOL)
                .thenApply(n -> n * 2)
                .thenApply(n -> "Result: " + n)
                .thenAccept(System.out::println)
                .join();  // Result: 10

        // Composing: thenCompose (flatMap)
        CompletableFuture<String> result = fetchUser(42L)
                .thenCompose(user -> fetchOrders(user));
        System.out.println(result.join());  // User-42 has 3 orders

        // Combining: thenCombine
        var f1 = CompletableFuture.supplyAsync(() -> "Hello");
        var f2 = CompletableFuture.supplyAsync(() -> "World");
        String combined = f1.thenCombine(f2, (a, b) -> a + " " + b).join();
        System.out.println(combined);  // Hello World

        // allOf — wait for multiple futures
        var futures = IntStream.range(1, 6)
                .mapToObj(i -> CompletableFuture.supplyAsync(() -> {
                    simulateDelay(100);
                    return i;
                }, CUSTOM_POOL))
                .toArray(CompletableFuture[]::new);

        var allDone = CompletableFuture.allOf(futures)
                .thenApply(v -> Stream.of(futures)
                        .map(CompletableFuture::join)
                        .toList());
        System.out.println(allDone.join());  // [1, 2, 3, 4, 5]

        // Error handling: exceptionally
        String safeResult = CompletableFuture
                .supplyAsync(() -> { throw new RuntimeException("Oops"); })
                .exceptionally(ex -> "Fallback: " + ex.getMessage())
                .join();
        System.out.println(safeResult);  // Fallback: Oops

        // Clean up
        CUSTOM_POOL.shutdown();
    }
}
"""),

    # ═══════════════════════════════════════════════════════════
    # 20. Modules & JPMS
    # ═══════════════════════════════════════════════════════════
    ("java/jpms-modules.md", "java", ["pattern", "architecture"],
     "Modules & JPMS", "module-info.java with exports/requires/opens/provides, and Module API introspection.", "pattern",
     """// --- module-info.java for com.example.app ---
module com.example.app {
    // Dependencies
    requires com.example.service;
    requires com.fasterxml.jackson.databind;
    requires org.slf4j;

    // Package access
    exports com.example.app.api;
    exports com.example.app.dto;

    // Open for reflective access (Jackson, Hibernate, etc.)
    opens com.example.app.dto to com.fasterxml.jackson.databind;

    // Service provider
    provides com.example.app.spi.ReportGenerator
        with com.example.app.reporting.PdfReportGenerator;
}

// --- module-info.java for com.example.service ---
module com.example.service {
    exports com.example.service.api;

    // Qualified export — only visible to listed modules
    exports com.example.service.internal to com.example.app;
}

// --- Java code using Module API ---
import java.lang.module.ModuleDescriptor;
import java.util.stream.*;

public class JpmsDemo {
    public static void main(String[] args) {
        // Module API introspection
        Module myModule = JpmsDemo.class.getModule();
        System.out.println("Module name: " + myModule.getName());
        System.out.println("Is named: " + myModule.isNamed());
        System.out.println("Is exported: " +
                myModule.isExported("java.snippets"));

        // List exported packages
        ModuleDescriptor descriptor = myModule.getDescriptor();
        if (descriptor != null) {
            System.out.println("\\nExported packages:");
            descriptor.exports().forEach(ex -> {
                System.out.println("  " + ex.source() +
                    (ex.isQualified()
                        ? " -> " + ex.targets().stream().collect(Collectors.joining(","))
                        : " (unqualified)"));
            });

            System.out.println("\\nRequired modules:");
            descriptor.requires().forEach(req ->
                    System.out.println("  " + req.name() +
                            " (" + req.modifiers() + ")"));
        }

        // Boot layer modules (built-in)
        System.out.println("\\nBoot layer modules (first 5):");
        ModuleLayer.boot().modules()
                .map(Module::getName)
                .limit(5)
                .forEach(System.out::println);
    }
}
"""),
]
