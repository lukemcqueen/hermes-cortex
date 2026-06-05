---
language: kotlin
tags: [kotlin, serialization, Serializable, Json, file-io, java.nio.file, use]
title: File I/O & Serialization
description: Shows Kotlin I/O with java.nio.file, kotlinx.serialization for JSON, and the 'use' extension for Closeable resources.
source: pattern
---

```kotlin
import kotlinx.serialization.*
import kotlinx.serialization.json.Json
import java.nio.file.*

@Serializable
data class Person(val name: String, val age: Int, val email: String? = null)

val json = Json { prettyPrint = true; ignoreUnknownKeys = true }

// Write JSON to file
fun writePeople(people: List<Person>, path: Path) {
    Files.writeString(path, json.encodeToString(people))
}

// Read JSON from file
fun readPeople(path: Path): List<Person> {
    val content = Files.readString(path)
    return json.decodeFromString<List<Person>>(content)
}

// 'use' for Closeable
fun readLines(path: Path): List<String> =
    Files.newBufferedReader(path).use { reader ->
        reader.readLines()
    }

// Walk directory tree
fun walkTree(root: Path): Sequence<Path> =
    Files.walk(root).use { it.toList().asSequence() }

fun main() {
    val dir = Path.of("/tmp/data")
    Files.createDirectories(dir)
    val file = dir.resolve("people.json")

    val people = listOf(
        Person("Alice", 30),
        Person("Bob", 25, "bob@example.com")
    )

    writePeople(people, file)
    val loaded = readPeople(file)
    println(loaded)

    // Cleanup
    Files.deleteIfExists(file)
}

```
