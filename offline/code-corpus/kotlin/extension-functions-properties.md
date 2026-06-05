---
language: kotlin
tags: [kotlin, extension-function, extension-property, infix, operator-overloading]
title: Extension Functions & Properties
description: Shows Kotlin extension functions, extension properties, infix notation, and operator overloading.
source: pattern
---

```kotlin
// Extension function
fun String.wordCount(): Int =
    trim().split("\s+".toRegex()).size

// Extension property
val String.isEmail: Boolean
    get() = matches(Regex("^[A-Za-z0-9+_.-]+@(.+)$"))

// Generic extension
fun <T> List<T>.secondOrNull(): T? =
    if (size >= 2) this[1] else null

// Infix extension
infix fun String.repeat(times: Int): String =
    buildString { repeat(times) { append(this@repeat) } }

// Operator overloading
data class Vector(val x: Int, val y: Int) {
    operator fun plus(other: Vector) = Vector(x + other.x, y + other.y)
    operator fun times(scalar: Int) = Vector(x * scalar, y * scalar)
    operator fun compareTo(other: Vector): Int =
        (x * x + y * y) compareTo (other.x * other.x + other.y * other.y)
}

fun main() {
    println("Hello world!".wordCount())       // 2
    println("test@example.com".isEmail)       // true
    println(listOf(1).secondOrNull())         // null

    println("ha" repeat 3)                    // hahaha

    val v1 = Vector(1, 2)
    val v2 = Vector(3, 4)
    println(v1 + v2)                          // Vector(x=4, y=6)
    println(v1 * 3)                           // Vector(x=3, y=6)
    println(v1 < v2)                          // true (shorter magnitude)
}

```
