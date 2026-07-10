---
language: kotlin
tags: [kotlin, listOf, mapOf, filter, map, fold, groupBy, chunked, sequence]
title: Collections & Sequences
description: Covers Kotlin collection operations: listOf/mapOf, filter/map/fold/groupBy/chunked, Sequence for lazy evaluation, and common functional patterns.
source: pattern
---

```kotlin
val numbers = listOf(1, 2, 3, 4, 5, 6)

// map / filter
val doubled = numbers.map { it * 2 }
val evens = numbers.filter { it % 2 == 0 }

// fold — accumulate
val sum = numbers.fold(0) { acc, n -> acc + n }

// groupBy
val grouped = numbers.groupBy { if (it % 2 == 0) "even" else "odd" }

// chunked — split into batches
val batches = numbers.chunked(2) // [[1,2], [3,4], [5,6]]

// Map operations
val map = mapOf("a" to 1, "b" to 2, "c" to 3)
val transformed = map.mapValues { (_, v) -> v * 2 }

// Sequence — lazy evaluation
val result = sequenceOf(1, 2, 3, 4, 5)
    .map {
        println("mapping $it")
        it * 2
    }
    .filter {
        println("filtering $it")
        it > 5
    }
    .toList() // terminal operation triggers evaluation

// flatMap
val nested = listOf(listOf(1, 2), listOf(3, 4))
val flattened = nested.flatMap { it }

// zipWithNext
val deltas = numbers.zipWithNext { a, b -> b - a }

fun main() {
    println(flattened) // [1, 2, 3, 4]
}

```
