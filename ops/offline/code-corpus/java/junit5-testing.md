---
language: java
tags: [pattern, testing]
title: JUnit 5 Testing
description: @Test, @ParameterizedTest, @BeforeEach, assertions, @Mock with Mockito, and assertThrows.
source: pattern
---

```java
import org.junit.jupiter.api.*;
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

```
