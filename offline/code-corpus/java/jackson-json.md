---
language: java
tags: [pattern, io, framework]
title: JSON Processing (Jackson)
description: ObjectMapper, @JsonProperty, readValue/writeValueAsString, Jackson annotations for serialization.
source: pattern
---

```java
import com.fasterxml.jackson.annotation.*;
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

```
