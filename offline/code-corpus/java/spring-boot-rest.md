---
language: java
tags: [pattern, framework]
title: Spring Boot REST API
description: @RestController, @GetMapping/PostMapping, @RequestBody, @PathVariable, and @Service layered architecture.
source: pattern
---

```java
import org.springframework.boot.SpringApplication;
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

```
