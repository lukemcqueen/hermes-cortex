---
language: kotlin
tags: [kotlin, lambda, higher-order, inline, crossinline, noinline, extension-function]
title: Functions & Lambdas
description: Covers Kotlin functions: lambda syntax, 'it' implicit argument, higher-order functions, inline/crossinline/noinline modifiers, and extension functions.
source: pattern
---

```kotlin
// Lambda basics
val square: (Int) -> Int = { x -> x * x }
val cube: (Int) -> Int = { it * it * it }

// Higher-order function
fun <T, R> List<T>.transform(block: (T) -> R): List<R> = map(block)

// Extension function
fun String.isPalindrome(): Boolean =
    this == reversed()

// Infix function
infix fun Int.plusTimes(other: Int): Int = (this + other) * 2

// Inline function
inline fun measureTime(block: () -> Unit): Long {
    val start = System.nanoTime()
    block()
    return System.nanoTime() - start
}

// crossinline — no non-local return
inline fun runWithLog(crossinline block: () -> Unit) {
    println("start")
    block()
    println("end")
}

// noinline — pass lambda as value
inline fun conditional(
    noinline body: () -> Unit,
    condition: Boolean
) {
    if (condition) body()
}

fun main() {
    println("Racecar".isPalindrome())   // true
    println(3 plusTimes 4)              // 14
    println(square(5))                  // 25
}

```
