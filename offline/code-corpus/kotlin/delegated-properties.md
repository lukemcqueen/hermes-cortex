---
language: kotlin
tags: [kotlin, delegated-property, by-lazy, Delegates.observable, by-map, Compose]
title: Delegated Properties
description: Shows Kotlin delegated properties: by lazy, Delegates.observable, by map, and by remember in Compose.
source: pattern
---

```kotlin
import kotlin.properties.Delegates

// Lazy initialization — computed once on first access
val heavyComputation: String by lazy {
    println("Computing...")
    "Result: ${(1..100_000).sum()}"
}

// Observable delegate — fires on every change
var watched: String by Delegates.observable("initial") { _, old, new ->
    println("$old -> $new")
}

// Vetoable — can reject changes
var positive: Int by Delegates.vetoable(0) { _, _, new -> new >= 0 }

// Delegate to a Map (useful for deserialization)
class User(map: Map<String, Any?>) {
    val name: String by map
    val age: Int by map
}

// Custom delegate
class Logged<String> {
    private var value: String? = null

    operator fun getValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>): String {
        println("GET ${property.name} = $value")
        return value ?: "default"
    }

    operator fun setValue(thisRef: Any?, property: kotlin.reflect.KProperty<*>, newValue: String) {
        println("SET ${property.name} = $newValue")
        value = newValue
    }
}

var logged by Logged<String>()

fun main() {
    println(heavyComputation)  // computes once
    println(heavyComputation)  // cached

    watched = "hello"          // initial -> hello
    watched = "world"          // hello -> world

    logged = "test"            // SET logged = test
    println(logged)            // GET logged = test

    val user = User(mapOf("name" to "Alice", "age" to 30))
    println(user.name)         // Alice
}

```
