---
language: java
tags: [pattern, meta]
title: Annotations & Reflection
description: @Retention, @Target, custom annotation, Method.getAnnotation, field access via reflection.
source: pattern
---

```java
import java.lang.annotation.*;
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
                System.out.printf("  "%s": "%s", required=%b%n",
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

```
